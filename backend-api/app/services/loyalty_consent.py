"""Whether a phone number may be tied to sales and points.

Option 1 of docs/Reglementation/ARTCI.md: a customer is recognised by a phone
number only after agreeing to it, either in the customer app (proved by the
sign-in code) or at a counter (the merchant asks, the customer says yes, the
merchant ticks the box). Until then a sale is recorded, but anonymously: the
Wave webhook does not attach the sender's number, and a counter sale with a
number but no consent is refused so the merchant can ask.

Withdrawing is erasure, not just "stop": the points are deleted and past sales
lose the number. Article 14 consent that could not be taken back would not be
consent.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models

# Bumped whenever the text shown to customers changes, so each row says which
# wording was agreed to. The apps send the version they displayed.
CURRENT_VERSION = "fidelite-2026-10"

APP = "app"
COUNTER = "counter"


async def _row(db: AsyncSession, customer_id: str) -> models.LoyaltyConsent | None:
    return (
        await db.execute(select(models.LoyaltyConsent).where(models.LoyaltyConsent.customer_id == customer_id))
    ).scalar_one_or_none()


async def has_consent(db: AsyncSession, customer_id: str) -> bool:
    row = await _row(db, customer_id)
    return row is not None and row.withdrawn_at is None


async def current(db: AsyncSession, customer_id: str) -> models.LoyaltyConsent | None:
    row = await _row(db, customer_id)
    return row if row is not None and row.withdrawn_at is None else None


async def grant(
    db: AsyncSession, customer_id: str, *, source: str, version: str, now: datetime, venue_id: int | None = None
) -> models.LoyaltyConsent:
    """Record consent, or renew a withdrawn one. An active consent is kept as
    it was: the first agreement is the one on file."""
    row = await _row(db, customer_id)
    if row is None:
        row = models.LoyaltyConsent(
            customer_id=customer_id, source=source, venue_id=venue_id, consent_version=version, granted_at=now
        )
        db.add(row)
    elif row.withdrawn_at is not None:
        row.source, row.venue_id, row.consent_version = source, venue_id, version
        row.granted_at, row.withdrawn_at = now, None
    return row


async def withdraw(db: AsyncSession, customer_id: str, now: datetime) -> int:
    """Withdraw consent and erase what it allowed. Returns the points deleted.

    Sales stay in the merchant's history (they are the merchant's records) but
    no longer name the customer. Pending checkouts are left alone: they are
    payments in flight, not loyalty data. The caller commits."""
    row = await _row(db, customer_id)
    if row is not None and row.withdrawn_at is None:
        row.withdrawn_at = now
    entries = (
        await db.execute(select(models.LoyaltyEntry).where(models.LoyaltyEntry.customer_id == customer_id))
    ).scalars().all()
    points = sum(e.points for e in entries)
    entry_ids = [e.id for e in entries]
    if entry_ids:
        await db.execute(
            update(models.SaleEvent)
            .where(models.SaleEvent.loyalty_entry_id.in_(entry_ids))
            .values(loyalty_entry_id=None)
        )
    await db.execute(
        update(models.SaleEvent).where(models.SaleEvent.customer_id == customer_id).values(customer_id=None)
    )
    await db.execute(delete(models.LoyaltyEntry).where(models.LoyaltyEntry.customer_id == customer_id))
    return points
