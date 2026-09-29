"""Merchant side of QR payments: show a QR for an amount, see it get paid."""

import secrets
from datetime import timedelta

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.entitlements import max_stats_days
from ..core.security import require_role
from ..db import get_db
from ..schemas.customer import DayTotal, MerchantStatsOut, PaymentRequestIn, PaymentRequestOut
from .customer import new_pay_code, qr_payload, utcnow

router = APIRouter()

# Long enough to hand over the phone and confirm; short enough that a photo of
# the screen is useless by the time anyone could misuse it.
REQUEST_TTL = timedelta(minutes=10)


async def _my_venue(db: AsyncSession, user, require_wallet: bool = True) -> models.Venue:
    venue = (
        await db.execute(select(models.Venue).where(models.Venue.owner_username == user["username"]))
    ).scalars().first()
    if venue is None:
        raise HTTPException(status_code=404, detail="Votre compte n'est lie a aucun commerce")
    if require_wallet and not (venue.payout_provider and venue.payout_account):
        raise HTTPException(status_code=422, detail="Ajoutez d'abord votre numero mobile money pour recevoir des paiements")
    return venue


def _out(r: models.PaymentRequest) -> PaymentRequestOut:
    return PaymentRequestOut(
        id=r.id,
        code=r.code,
        qr_payload=qr_payload(r.code),
        amount=r.amount,
        status=r.status,
        venue_name=r.venue.name,
        created_at=r.created_at,
        expires_at=r.expires_at,
        paid_at=r.payment.completed_at if r.status == "paid" and r.payment else None,
        wallet_provider=r.payment.wallet_provider if r.status == "paid" and r.payment else None,
        points_awarded=r.payment.points_awarded if r.status == "paid" and r.payment else None,
    )


async def _load(db: AsyncSession, request_id: int, user) -> models.PaymentRequest:
    r = (
        await db.execute(
            select(models.PaymentRequest)
            .options(selectinload(models.PaymentRequest.venue), selectinload(models.PaymentRequest.payment))
            .where(models.PaymentRequest.id == request_id)
        )
    ).scalar_one_or_none()
    # Another merchant's request answers exactly like a missing one.
    if r is None or r.venue.owner_username != user["username"]:
        raise HTTPException(status_code=404, detail="request not found")
    if r.status == "open" and r.expires_at <= utcnow():
        r.status = "expired"
        await db.commit()
    return r


@router.post("/merchant/payment-requests", response_model=PaymentRequestOut, status_code=201)
async def create_request(payload: PaymentRequestIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user)
    now = utcnow()
    for _ in range(3):  # a code collision is ~impossible; retry rather than 500 if it happens
        r = models.PaymentRequest(
            code=new_pay_code(), venue_id=venue.id, amount=payload.amount,
            status="open", created_at=now, expires_at=now + REQUEST_TTL,
        )
        db.add(r)
        try:
            await db.commit()
            break
        except IntegrityError:
            await db.rollback()
    return _out(await _load(db, r.id, user))


@router.get("/merchant/payment-requests/{request_id}", response_model=PaymentRequestOut)
async def get_request(request_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    """Polled by the merchant's QR screen until the status leaves `open`."""
    return _out(await _load(db, request_id, user))


@router.post("/merchant/payment-requests/{request_id}/cancel", response_model=PaymentRequestOut)
async def cancel_request(request_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    r = await _load(db, request_id, user)
    if r.status == "open":
        r.status = "cancelled"
        await db.commit()
    elif r.status in ("processing", "paid"):
        raise HTTPException(status_code=409, detail="Trop tard : le client est en train de payer ou a paye")
    return _out(await _load(db, r.id, user))


@router.get("/merchant/stats", response_model=MerchantStatsOut)
async def merchant_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("merchant")),
):
    """Money received through Djassa over the last `days` days.

    Aggregated in Python rather than SQL: a single venue's month is a few
    hundred rows, and it keeps the day bucketing identical on SQLite (dev)
    and Postgres (prod).

    The *window* is what the plan gates, never the recording underneath it: a
    starter merchant still records every sale and still earns their customers
    points, they just cannot read further back than a week
    (app/core/entitlements.py explains why that line is drawn there).
    """
    venue = await _my_venue(db, user, require_wallet=False)
    from .billing import subscription_for  # local: billing imports _my_venue from here

    allowed = max_stats_days(await subscription_for(db, venue.id))
    if allowed is not None and days > allowed:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Votre formule affiche {allowed} jours d'historique. "
                "Passez a la formule Croissance pour voir plus loin."
            ),
        )
    now = utcnow()
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    payments = (
        await db.execute(
            select(models.CustomerPayment).where(
                models.CustomerPayment.venue_id == venue.id,
                models.CustomerPayment.status == "succeeded",
                models.CustomerPayment.completed_at >= since,
            )
        )
    ).scalars().all()
    redeemed = (
        await db.execute(
            select(models.LoyaltyEntry).where(
                models.LoyaltyEntry.venue_id == venue.id,
                models.LoyaltyEntry.reason == "redeem",
                models.LoyaltyEntry.created_at >= since,
            )
        )
    ).scalars().all()

    per_customer = Counter(p.customer_id for p in payments)
    returning = {c for c, n in per_customer.items() if n > 1}
    by_day: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_wallet: Counter = Counter()
    for p in payments:
        bucket = by_day[p.completed_at.date().isoformat()]
        bucket[0] += p.amount
        bucket[1] += 1
        by_wallet[p.wallet_provider] += p.amount

    revenue = sum(p.amount for p in payments)
    todays = [p for p in payments if p.completed_at >= today]
    return MerchantStatsOut(
        venue_name=venue.name,
        days=days,
        revenue=revenue,
        payments=len(payments),
        average_basket=revenue // len(payments) if payments else 0,
        customers=len(per_customer),
        returning_customers=len(returning),
        returning_revenue=sum(p.amount for p in payments if p.customer_id in returning),
        points_issued=sum(p.points_awarded for p in payments),
        rewards_redeemed=len(redeemed),
        today_revenue=sum(p.amount for p in todays),
        today_payments=len(todays),
        # Every day in the range, zeros included, so a chart has no gaps.
        by_day=[
            DayTotal(day=d, amount=by_day[d][0] if d in by_day else 0, count=by_day[d][1] if d in by_day else 0)
            for d in ((since + timedelta(days=i)).date().isoformat() for i in range(days))
        ],
        by_wallet=dict(by_wallet),
    )
