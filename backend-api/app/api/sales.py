"""Recording a cash sale into the one event stream.

This replaces `POST /api/transactions` for the retailer app. The difference that
matters is what is *absent* from the request: there is no `merchant_id`. The
venue is derived from the merchant's token, so a client can no longer assert
which business a sale belongs to -- which it could, and did, before
(docs/optimization_claude_djassa.md, finding 2).

Never gated by plan. Recording is the habit every other feature and the whole
financing case depend on (app/core/entitlements.py).
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.security import require_role
from ..db import get_db
from ..schemas.customer import SaleIn, SaleOut, SaleSyncIn, SaleSyncOut, SaleSyncResult
from ..services import sale_events
from .customer import utcnow
from .payment_requests import _my_venue

router = APIRouter()


def _naive_utc(value: datetime | None) -> datetime | None:
    """The column is `TIMESTAMP WITHOUT TIME ZONE`; asyncpg refuses a tz-aware
    value outright rather than silently dropping the offset, so every
    `occurred_at` from a client (always tz-aware -- Flutter sends `...Z`) has
    to be converted here before it reaches the model."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value


def _out(event: models.SaleEvent) -> SaleOut:
    return SaleOut(
        id=event.id,
        venue_id=event.venue_id,
        source=event.source,
        amount=event.amount,
        currency=event.currency,
        type=event.type,
        occurred_at=event.occurred_at,
        recorded_at=event.recorded_at,
        idempotency_key=event.idempotency_key,
    )


async def _record(db: AsyncSession, venue_id: int, payload: SaleIn, username: str) -> tuple[models.SaleEvent, bool]:
    """Record one declared sale, or return the existing one for a reused key.

    A key reused with *different* contents is a conflict, not a duplicate: the
    caller has two different sales sharing a key, and answering with the first
    one would quietly lose the second.

    Takes `venue_id`, not the venue: `sync_sales` rolls back between operations,
    which expires every loaded instance, and reading `venue.id` off an expired
    one attempts synchronous IO under asyncio and fails.
    """
    occurred_at = _naive_utc(payload.occurred_at)
    event, existed = await sale_events.record_declared_sale(
        db,
        venue_id=venue_id,
        amount=payload.amount,
        currency=payload.currency,
        type_=payload.type,
        client_key=payload.idempotency_key,
        recorded_by=username,
        occurred_at=occurred_at,
        now=utcnow(),
    )
    if existed:
        fingerprint = sale_events.declared_hash(
            amount=payload.amount,
            currency=payload.currency,
            type_=payload.type,
            occurred_at=occurred_at,
        )
        if event.venue_id != venue_id or event.idempotency_hash != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key already used")
    return event, existed


@router.post("/merchant/sales", response_model=SaleOut, status_code=201)
async def record_sale(payload: SaleIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    """Record one cash sale. Idempotent on `idempotency_key`."""
    venue = await _my_venue(db, user, require_wallet=False)
    event, _ = await _record(db, venue.id, payload, user["username"])
    await db.commit()
    await db.refresh(event)
    return _out(event)


@router.post("/merchant/sales/sync", response_model=SaleSyncOut)
async def sync_sales(payload: SaleSyncIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    """Drain the device's offline queue in one request.

    Each operation is committed separately and reported separately, so one bad
    row cannot block the rest of a batch -- the behaviour the retailer app's
    queue already relies on.
    """
    # Resolved once, as a plain int: the rollback below expires ORM instances.
    venue_id = (await _my_venue(db, user, require_wallet=False)).id
    results: list[SaleSyncResult] = []
    for operation in payload.operations:
        try:
            event, existed = await _record(db, venue_id, operation, user["username"])
            await db.commit()
            await db.refresh(event)
            results.append(
                SaleSyncResult(
                    idempotency_key=operation.idempotency_key,
                    status="already_processed" if existed else "accepted",
                    sale=_out(event),
                )
            )
        except HTTPException as exc:
            await db.rollback()
            results.append(
                SaleSyncResult(idempotency_key=operation.idempotency_key, status="rejected", error=str(exc.detail))
            )
        except IntegrityError:
            # Two devices, or two passes, racing the same key: whoever lost reads
            # the winner's row rather than reporting a failure for a stored sale.
            await db.rollback()
            existing = await sale_events.find_declared(db, operation.idempotency_key)
            if existing is not None:
                results.append(
                    SaleSyncResult(
                        idempotency_key=operation.idempotency_key,
                        status="already_processed",
                        sale=_out(existing),
                    )
                )
            else:
                results.append(
                    SaleSyncResult(
                        idempotency_key=operation.idempotency_key,
                        status="rejected",
                        error="operation could not be processed",
                    )
                )
        except Exception:
            await db.rollback()
            results.append(
                SaleSyncResult(
                    idempotency_key=operation.idempotency_key,
                    status="rejected",
                    error="operation could not be processed",
                )
            )
    return SaleSyncOut(results=results)


@router.get("/admin/sale-events/quarantined")
async def list_quarantined(
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    """Declared sales the migration could not attach to a venue.

    Migration `0014_sale_events` refused to guess a mapping, so these are real
    recorded amounts belonging to nobody we can name. They are excluded from
    every revenue figure until a human resolves them; this is where the backlog
    is visible instead of buried in a migration log.
    """
    total = (
        await db.execute(
            select(func.count(models.SaleEvent.id)).where(models.SaleEvent.status == sale_events.QUARANTINED)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(models.SaleEvent)
            .where(models.SaleEvent.status == sale_events.QUARANTINED)
            .order_by(models.SaleEvent.occurred_at.desc(), models.SaleEvent.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    amount = (
        await db.execute(
            select(func.coalesce(func.sum(models.SaleEvent.amount), 0)).where(
                models.SaleEvent.status == sale_events.QUARANTINED
            )
        )
    ).scalar_one()
    return {
        "total": int(total),
        "total_amount": str(Decimal(amount)),
        "events": [
            {
                "id": e.id,
                "source": e.source,
                "amount": str(e.amount),
                "currency": e.currency,
                "occurred_at": e.occurred_at,
                "recorded_by": e.recorded_by,
                "legacy_merchant_id": e.legacy_merchant_id,
                "legacy_transaction_id": e.legacy_transaction_id,
            }
            for e in rows
        ],
    }
