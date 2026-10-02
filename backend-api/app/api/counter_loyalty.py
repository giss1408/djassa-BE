"""Loyalty at the counter, for customers identified by phone.

A customer who pays cash gives their number and earns points on the sale
(`POST /api/merchant/sales`). They may never install the customer app, so the
merchant must be able to tell them their balance and hand over a reward from
the merchant app. That is the whole loop the concept asks for: the customer is
recognised by phone, and comes back (docs/business/CONCEPT.md § 5).

Not merged into accounts that merely *declare* a number: a Tier 0 identity
profile does not prove it (`app/api/identity.py`), so that would let anyone
collect someone else's points. Phone + code sign-in (`app/api/auth.py`) does
prove it, and its token subject is this same `tel:` key, so a customer who
signs in that way sees these points with no merge step.

Scoped to the merchant's own venue in both directions: points are per venue
(a maquis funds its own rewards), so a merchant can read and spend only the
points their venue issued, and only on their own rewards.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.phone import InvalidPhone, mask_phone, normalize_phone, phone_key
from ..core.security import require_role
from ..db import get_db
from ..schemas.customer import CounterCustomerIn, CounterLoyaltyOut, CounterRedeemIn, RedeemOut, RewardOut
from .customer import _VOUCHER_ALPHABET, _balance, utcnow
from .payment_requests import _my_venue

router = APIRouter()


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidPhone as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/merchant/customers/loyalty", response_model=CounterLoyaltyOut)
async def counter_balance(
    payload: CounterCustomerIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))
):
    """The customer's points at this venue, and the rewards they can take."""
    venue = await _my_venue(db, user, require_wallet=False)
    e164 = _phone(payload.phone)
    rewards = (
        await db.execute(
            select(models.LoyaltyReward)
            .where(models.LoyaltyReward.venue_id == venue.id, models.LoyaltyReward.active.is_(True))
            .order_by(models.LoyaltyReward.cost_points)
        )
    ).scalars().all()
    return CounterLoyaltyOut(
        customer=mask_phone(e164),
        points=await _balance(db, phone_key(e164), venue.id),
        rewards=[RewardOut.model_validate(r) for r in rewards],
    )


@router.post("/merchant/customers/redeem", response_model=RedeemOut, status_code=201)
async def counter_redeem(
    payload: CounterRedeemIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))
):
    """Hand a reward to a phone-identified customer at the counter.

    The balance check and the debit happen under a row lock on the venue, so
    two taps of "Donner" (or two staff phones) cannot spend the same points
    twice.
    """
    venue = await _my_venue(db, user, require_wallet=False)
    e164 = _phone(payload.phone)
    reward = (
        await db.execute(
            select(models.LoyaltyReward)
            .options(selectinload(models.LoyaltyReward.venue))
            .where(models.LoyaltyReward.id == payload.reward_id)
        )
    ).scalar_one_or_none()
    if reward is None or not reward.active or reward.venue_id != venue.id:
        raise HTTPException(status_code=404, detail="reward not found")

    # Serialise redemptions per venue. A no-op on SQLite (tests), a real lock
    # on PostgreSQL, where concurrent requests actually happen.
    await db.execute(select(models.Venue.id).where(models.Venue.id == venue.id).with_for_update())
    key = phone_key(e164)
    balance = await _balance(db, key, venue.id)
    if balance < reward.cost_points:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"not enough points: {balance} of {reward.cost_points}",
        )

    code = "".join(secrets.choice(_VOUCHER_ALPHABET) for _ in range(6))
    db.add(
        models.LoyaltyEntry(
            customer_id=key,
            venue_id=venue.id,
            points=-reward.cost_points,
            reason="redeem",
            reward_id=reward.id,
            voucher_code=code,
            created_at=utcnow(),
        )
    )
    await db.commit()
    return RedeemOut(
        voucher_code=code,
        reward_title=reward.title,
        venue_name=reward.venue.name,
        points_spent=reward.cost_points,
        remaining_points=balance - reward.cost_points,
    )
