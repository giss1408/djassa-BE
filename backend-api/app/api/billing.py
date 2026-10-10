"""Merchant subscriptions: what a venue is on, and what they have paid.

Collection is manual in the pilot -- the merchant transfers by mobile money and
an admin records it here. That is deliberate: the recurring-collection code
belongs with the aggregator integration, and the pilot needs the *record* long
before it needs the automation, because "merchants pay or renew" is the Phase 1
exit gate (docs/ROADMAP.md) and today nothing can answer it.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.entitlements import PAYING_STATUSES, PILOT_PLAN, PLAN_NAMES, effective_plan, max_stats_days
from ..core.security import require_role
from ..db import get_db
from ..schemas.billing import (
    BillingEventOut,
    BillingPaymentIn,
    RevenueSummaryOut,
    SubscriptionIn,
    SubscriptionOut,
)
from .customer import utcnow
from .payment_requests import _my_venue

router = APIRouter()

_STATUSES = ("trialing", "active", "past_due", "cancelled")


async def subscription_for(db: AsyncSession, venue_id: int) -> models.MerchantSubscription | None:
    """The venue's live subscription, or None. Cancelled rows are history."""
    return (
        await db.execute(
            select(models.MerchantSubscription)
            .where(
                models.MerchantSubscription.venue_id == venue_id,
                models.MerchantSubscription.status != "cancelled",
            )
            .order_by(models.MerchantSubscription.id.desc())
        )
    ).scalars().first()


def _out(venue: models.Venue, sub: models.MerchantSubscription | None) -> SubscriptionOut:
    plan = effective_plan(sub)
    from ..core.entitlements import _PLANS

    return SubscriptionOut(
        venue_id=venue.id,
        venue_name=venue.name,
        plan=plan,
        status=sub.status if sub else "none",
        amount=sub.amount if sub else 0,
        currency=sub.currency if sub else "XOF",
        period=sub.period if sub else "monthly",
        current_period_start=sub.current_period_start if sub else None,
        current_period_end=sub.current_period_end if sub else None,
        started_at=sub.started_at if sub else None,
        cancelled_at=sub.cancelled_at if sub else None,
        features=sorted(f.value for f in _PLANS[plan]),
        max_stats_days=max_stats_days(sub),
    )


async def _venue_by_id(db: AsyncSession, venue_id: int) -> models.Venue:
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    return venue


# --- Merchant: my own plan, read-only -----------------------------------------


@router.get("/merchant/subscription", response_model=SubscriptionOut)
async def my_subscription(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    """Read-only on purpose: a merchant cannot put themselves on a better plan."""
    venue = await _my_venue(db, user, require_wallet=False)
    return _out(venue, await subscription_for(db, venue.id))


@router.get("/merchant/billing/events", response_model=list[BillingEventOut])
async def my_billing_events(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("merchant")),
):
    venue = await _my_venue(db, user, require_wallet=False)
    sub = await subscription_for(db, venue.id)
    if sub is None:
        return []
    rows = (
        await db.execute(
            select(models.BillingEvent)
            .where(models.BillingEvent.subscription_id == sub.id)
            .order_by(models.BillingEvent.occurred_at.desc(), models.BillingEvent.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [BillingEventOut.model_validate(r) for r in rows]


# --- Admin: selling and collecting --------------------------------------------


@router.put("/admin/venues/{venue_id}/subscription", response_model=SubscriptionOut)
async def set_subscription(
    venue_id: int, payload: SubscriptionIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))
):
    """Put a venue on a plan, or change the one it is on."""
    if payload.plan not in PLAN_NAMES:
        raise HTTPException(status_code=422, detail=f"plan must be one of {PLAN_NAMES}")
    if payload.status is not None and payload.status not in _STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {_STATUSES}")
    if payload.plan == PILOT_PLAN and payload.amount != 0:
        # The pilot is free for every merchant; a price here would raise an
        # invoice and, once active, count as revenue the pilot never earned.
        raise HTTPException(status_code=422, detail="Le pilote est gratuit : le montant doit etre 0")

    venue = await _venue_by_id(db, venue_id)
    now = utcnow()
    sub = await subscription_for(db, venue.id)
    if sub is None:
        sub = models.MerchantSubscription(
            venue_id=venue.id,
            plan=payload.plan,
            status=payload.status or "trialing",
            amount=payload.amount,
            currency=payload.currency,
            period=payload.period,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            started_at=now,
            created_at=now,
        )
        db.add(sub)
    else:
        sub.plan = payload.plan
        sub.amount = payload.amount
        sub.currency = payload.currency
        sub.period = payload.period
        if payload.status is not None:
            sub.status = payload.status
            if payload.status == "cancelled":
                sub.cancelled_at = now
    await db.flush()
    # An invoice is what makes the money owed visible; without it a plan change
    # is just a label and the unpaid list stays empty.
    if sub.amount > 0:
        db.add(
            models.BillingEvent(
                subscription_id=sub.id,
                kind="invoice_due",
                amount=sub.amount,
                currency=sub.currency,
                period_start=sub.current_period_start,
                period_end=sub.current_period_end,
                occurred_at=now,
                recorded_by=user["username"],
            )
        )
    await db.commit()
    return _out(venue, await subscription_for(db, venue.id))


@router.post("/admin/venues/{venue_id}/subscription/payments", response_model=SubscriptionOut)
async def record_payment(
    venue_id: int, payload: BillingPaymentIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))
):
    """Record a settled subscription payment and roll the period forward."""
    venue = await _venue_by_id(db, venue_id)
    sub = await subscription_for(db, venue.id)
    if sub is None:
        raise HTTPException(status_code=409, detail="Ce commerce n'a pas d'abonnement")

    now = utcnow()
    amount = payload.amount if payload.amount is not None else sub.amount
    db.add(
        models.BillingEvent(
            subscription_id=sub.id,
            kind="paid",
            amount=amount,
            currency=sub.currency,
            payment_reference=payload.payment_reference,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
            note=payload.note,
            occurred_at=now,
            recorded_by=user["username"],
        )
    )
    # Paying is what makes a trial or a lapsed account current again.
    sub.status = "active"
    # Roll from the period end, not from today, so a late payment does not hand
    # the merchant a free extension.
    base = sub.current_period_end if sub.current_period_end and sub.current_period_end > now else now
    sub.current_period_start = base
    sub.current_period_end = base + timedelta(days=30)
    await db.commit()
    return _out(venue, await subscription_for(db, venue.id))


@router.post("/admin/venues/{venue_id}/subscription/unpaid", response_model=SubscriptionOut)
async def mark_past_due(
    venue_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))
):
    """Mark a period unpaid. Does not remove the merchant's access to recording."""
    venue = await _venue_by_id(db, venue_id)
    sub = await subscription_for(db, venue.id)
    if sub is None:
        raise HTTPException(status_code=409, detail="Ce commerce n'a pas d'abonnement")
    sub.status = "past_due"
    db.add(
        models.BillingEvent(
            subscription_id=sub.id,
            kind="failed",
            amount=sub.amount,
            currency=sub.currency,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
            occurred_at=utcnow(),
            recorded_by=user["username"],
        )
    )
    await db.commit()
    return _out(venue, await subscription_for(db, venue.id))


@router.get("/admin/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    stmt = select(models.MerchantSubscription).options(selectinload(models.MerchantSubscription.venue))
    if status_filter:
        stmt = stmt.where(models.MerchantSubscription.status == status_filter)
    rows = (await db.execute(stmt.order_by(models.MerchantSubscription.id.desc()).limit(limit))).scalars().all()
    return [_out(s.venue, s) for s in rows]


@router.get("/admin/revenue", response_model=RevenueSummaryOut)
async def revenue_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    """MRR, plan mix and collection -- the Phase 1 exit gate, answerable at last."""
    since = utcnow() - timedelta(days=days)
    subs = (await db.execute(select(models.MerchantSubscription))).scalars().all()

    by_plan: dict[str, int] = {}
    by_status: dict[str, int] = {}
    mrr = 0
    paying = 0
    for s in subs:
        by_status[s.status] = by_status.get(s.status, 0) + 1
        plan = effective_plan(s)
        by_plan[plan] = by_plan.get(plan, 0) + 1
        # MRR counts money actually contracted: a trial is not revenue until it
        # converts, and counting it would overstate the one number the pilot
        # decision rests on.
        if s.status == "active" and s.amount > 0:
            mrr += s.amount
            paying += 1

    collected = (
        await db.execute(
            select(func.coalesce(func.sum(models.BillingEvent.amount), 0)).where(
                models.BillingEvent.kind == "paid", models.BillingEvent.occurred_at >= since
            )
        )
    ).scalar_one()

    # An invoice with no later `paid` event for the same period is still owed.
    invoices = (
        await db.execute(
            select(models.BillingEvent).where(models.BillingEvent.kind == "invoice_due")
        )
    ).scalars().all()
    paid_keys = {
        (e.subscription_id, e.period_start)
        for e in (
            await db.execute(select(models.BillingEvent).where(models.BillingEvent.kind == "paid"))
        ).scalars().all()
    }
    unpaid = [i for i in invoices if (i.subscription_id, i.period_start) not in paid_keys]

    currency = next((s.currency for s in subs if s.amount > 0), "XOF")
    return RevenueSummaryOut(
        active_paying_outlets=paying,
        mrr=mrr,
        currency=currency,
        outlets_by_plan=by_plan,
        outlets_by_status=by_status,
        collected_in_window=int(collected),
        window_days=days,
        unpaid_invoices=len(unpaid),
        unpaid_amount=sum(i.amount for i in unpaid),
    )
