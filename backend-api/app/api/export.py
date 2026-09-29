"""Consented export of a merchant's own activity.

Three rules, because this is the endpoint whose output would be handed to a
microfinance partner and it touches other people's transaction data:

1. **Ownership comes from the token, never the URL.** A merchant exports the
   venue they run, so there is no merchant id to tamper with.
2. **Consent is per data subject, and the default carries none.** The aggregate
   export answers "is this business real and regular", which is the actual
   underwriting question, without naming a single customer. Per-customer rows
   need each of those customers to have granted the scope.
3. **Every export is audited.** See models.ExportAudit.

Before this, `create_consent` recorded the *caller* as the consenting party and
the export checked only that the caller had consented for the requested merchant
id, so any account could self-grant and download any merchant's customer-level
history (docs/optimization_claude_djassa.md, finding 3).
"""

import csv
import io
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.security import get_current_user, require_role
from ..db import get_db
from ..schemas import ConsentIn, ConsentOut
from .customer import utcnow
from .payment_requests import _my_venue

router = APIRouter()

# The scope a customer grants to let their own rows leave in a merchant export.
CUSTOMER_ROWS_SCOPE = "transactions:export"

MAX_EXPORT_ROWS = 10_000


@router.post("/consents", response_model=ConsentOut, status_code=201)
async def create_consent(payload: ConsentIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Grant a consent for yourself.

    `user_id` in the body is ignored: consent is given by the person it binds,
    never recorded on someone else's behalf. Granting for a third party is how
    the old version let a caller authorize their own access to other people's data.
    """
    # Checked here rather than left to the foreign key: Postgres turns the
    # violation into a 500, and SQLite does not enforce it at all, so an unknown
    # merchant would silently produce a consent bound to nothing.
    if await db.get(models.Merchant, payload.merchant_id) is None:
        raise HTTPException(status_code=404, detail="merchant not found")
    consent = models.Consent(user_id=user["username"], merchant_id=payload.merchant_id, scope=payload.scope)
    db.add(consent)
    await db.flush()
    await db.commit()
    await db.refresh(consent)
    return ConsentOut(
        id=consent.id,
        user_id=consent.user_id,
        merchant_id=consent.merchant_id,
        scope=consent.scope,
        granted_at=consent.granted_at,
    )


@router.delete("/consents/{consent_id}", status_code=204)
async def withdraw_consent(consent_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Withdraw your own consent. Someone else's answers like a missing one."""
    consent = await db.get(models.Consent, consent_id)
    if consent is None or consent.user_id != user["username"]:
        raise HTTPException(status_code=404, detail="consent not found")
    await db.delete(consent)
    await db.commit()


async def _payments_in_window(db: AsyncSession, venue_id: int, days: int):
    since = (utcnow() - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        await db.execute(
            select(models.CustomerPayment)
            .where(
                models.CustomerPayment.venue_id == venue_id,
                models.CustomerPayment.status == "succeeded",
                models.CustomerPayment.completed_at >= since,
            )
            .order_by(models.CustomerPayment.completed_at)
            .limit(MAX_EXPORT_ROWS)
        )
    ).scalars().all(), since


@router.get("/export/merchant/revenue.csv")
async def export_revenue_summary(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("merchant")),
):
    """The merchant's own revenue, by day, with no customer identified.

    This is the default export and the one to show a lender: it answers
    regularity and volume, which is what underwriting asks, and it needs no
    customer's consent because it names none of them. A pseudonymous count of
    distinct payers is included because "how many repeat customers" is part of
    the same question -- a count is not an identity.
    """
    venue = await _my_venue(db, user, require_wallet=False)
    payments, since = await _payments_in_window(db, venue.id, days)

    by_day: dict[str, list] = defaultdict(lambda: [0, 0, set()])
    for p in payments:
        bucket = by_day[p.completed_at.date().isoformat()]
        bucket[0] += p.amount
        bucket[1] += 1
        bucket[2].add(p.customer_id)

    now = utcnow()
    db.add(
        models.ExportAudit(
            exported_by=user["username"],
            venue_id=venue.id,
            kind="revenue_summary",
            subject_count=0,
            row_count=len(by_day),
            period_start=since,
            period_end=now,
            occurred_at=now,
        )
    )
    await db.commit()

    def rows():
        buf = io.StringIO()
        w = csv.writer(buf)

        def flush():
            out = buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
            return out

        w.writerow(["venue", "currency", "period_start", "period_end"])
        w.writerow([venue.name, "XOF", since.date().isoformat(), now.date().isoformat()])
        w.writerow([])
        w.writerow(["date", "amount_total", "transactions", "distinct_customers"])
        yield flush()
        for day in sorted(by_day):
            total, count, customers = by_day[day]
            w.writerow([day, total, count, len(customers)])
            yield flush()

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="revenue-{venue.id}.csv"'},
    )


@router.get("/export/merchant/customers.csv")
async def export_customer_rows(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("merchant")),
):
    """Per-customer rows, restricted to customers who granted the scope.

    A customer who never consented is absent -- not anonymized, absent. If nobody
    consented the export is refused rather than returning an empty file, so the
    merchant learns that consent is the missing piece.
    """
    venue = await _my_venue(db, user, require_wallet=False)
    payments, since = await _payments_in_window(db, venue.id, days)

    # Consent is recorded against a merchant id; a venue may not have one, in
    # which case no customer can have consented to this venue's export yet.
    if venue.merchant_id is None:
        raise HTTPException(
            status_code=409,
            detail="Ce commerce n'est pas rattache a un identifiant marchand: aucun consentement client ne peut s'y rapporter",
        )

    consents = (
        await db.execute(
            select(models.Consent).where(
                models.Consent.merchant_id == venue.merchant_id,
                models.Consent.scope == CUSTOMER_ROWS_SCOPE,
            )
        )
    ).scalars().all()
    consented = {c.user_id: c for c in consents}
    if not consented:
        raise HTTPException(
            status_code=403,
            detail="Aucun client n'a consenti a l'export de ses transactions",
        )

    rows = [p for p in payments if p.customer_id in consented]
    now = utcnow()
    subjects = {p.customer_id for p in rows}
    db.add(
        models.ExportAudit(
            exported_by=user["username"],
            venue_id=venue.id,
            merchant_id=venue.merchant_id,
            kind="customer_rows",
            scope=CUSTOMER_ROWS_SCOPE,
            # Which consent authorized it; one row per export, so record the
            # first when several customers consented.
            consent_id=consented[sorted(subjects)[0]].id if subjects else None,
            subject_count=len(subjects),
            row_count=len(rows),
            period_start=since,
            period_end=now,
            occurred_at=now,
        )
    )
    await db.commit()

    def stream():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["customer_id", "amount", "currency", "wallet_provider", "completed_at", "points_awarded"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for p in rows:
            w.writerow(
                [
                    p.customer_id,
                    p.amount,
                    p.currency,
                    p.wallet_provider,
                    p.completed_at.isoformat() if p.completed_at else "",
                    p.points_awarded,
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        stream(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="customers-{venue.id}.csv"'},
    )


@router.get("/admin/export-audits")
async def list_export_audits(
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    """Who exported what. The answer a partner or a regulator asks for."""
    rows = (
        await db.execute(
            select(models.ExportAudit).order_by(models.ExportAudit.occurred_at.desc(), models.ExportAudit.id.desc()).limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": a.id,
            "exported_by": a.exported_by,
            "venue_id": a.venue_id,
            "merchant_id": a.merchant_id,
            "kind": a.kind,
            "scope": a.scope,
            "consent_id": a.consent_id,
            "subject_count": a.subject_count,
            "row_count": a.row_count,
            "period_start": a.period_start,
            "period_end": a.period_end,
            "occurred_at": a.occurred_at,
        }
        for a in rows
    ]
