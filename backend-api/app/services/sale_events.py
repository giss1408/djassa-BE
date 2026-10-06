"""Writing to the one sale stream.

Every sale reaches `sale_events` through here, so the evidence label is applied
in exactly one place and cannot drift between the confirmed path (a settled
mobile-money payment) and the declared path (a merchant recording cash).

The two rules this module exists to hold:

* **The caller never chooses `source`.** A confirmed event is written only from
  the settlement path, where the aggregator's answer is in hand. Anything a
  client posts is `cash_declared`, whatever the client says.
* **The caller never chooses the venue.** It comes from the merchant's token.
  The old declared stream took `merchant_id` from the request body, which is why
  the retailer app could post a hardcoded id and `/api/transactions` would
  create a merchant row to match it.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models

# The evidence classes. Never a free-form string at a call site.
CONFIRMED = "mobile_money_confirmed"
DECLARED = "cash_declared"

RECORDED = "recorded"
QUARANTINED = "quarantined"


def declared_key(client_key: str) -> str:
    """Namespace a client-chosen idempotency key.

    Confirmed events derive theirs from the payment id (`pay:12`), so without a
    prefix a client could pick `pay:12` and collide with one.
    """
    return f"sale:{client_key}"


def declared_hash(
    *, amount: Decimal, currency: str, type_: str, occurred_at: datetime | None, customer_id: str | None = None
) -> str:
    """Fingerprint of a declared sale, so a reused key with different contents
    is a conflict rather than a silent no-op returning someone else's row.

    The customer is appended only when present, so the fingerprint of every
    anonymous sale -- including all rows stored before customers could be
    attached -- is unchanged."""
    parts = f"{amount}|{currency.upper()}|{type_}|{occurred_at.isoformat() if occurred_at else ''}"
    if customer_id:
        parts += f"|{customer_id}"
    return hashlib.sha256(parts.encode()).hexdigest()


def cash_sale_points(amount: Decimal, currency: str, points_per_100: int | None) -> int:
    """Same rule as a mobile-money payment (`settle_payment`): the venue's
    points per full 100 F. Only XOF, the currency the rule is written in."""
    if currency.upper() != "XOF" or not points_per_100:
        return 0
    return int(Decimal(amount) // 100) * points_per_100


async def record_confirmed_sale(
    db: AsyncSession,
    *,
    payment: models.CustomerPayment,
    loyalty_entry: models.LoyaltyEntry | None,
    occurred_at: datetime,
) -> models.SaleEvent:
    """The event behind a settled mobile-money payment.

    Called from the settlement path inside the same transaction that grants the
    points, so one payment produces one event and one ledger entry atomically or
    neither. The unique `payment_id` is the second lock: a replayed webhook that
    somehow reached here twice would be refused by the database.
    """
    event = models.SaleEvent(
        venue_id=payment.venue_id,
        source=CONFIRMED,
        status=RECORDED,
        amount=payment.amount,
        currency=payment.currency,
        type="sale",
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        customer_id=payment.customer_id,
        payment_id=payment.id,
        loyalty_entry_id=loyalty_entry.id if loyalty_entry is not None else None,
        idempotency_key=f"pay:{payment.id}",
        created_at=occurred_at,
    )
    db.add(event)
    return event


async def record_wallet_sale(
    db: AsyncSession,
    *,
    venue_id: int,
    amount: int,
    idempotency_key: str,
    customer_id: str | None,
    points_per_100: int | None,
    now: datetime,
) -> models.SaleEvent:
    """A payment the merchant's own wallet reported (e.g. Wave's
    merchant.payment_received), made outside a Djassa checkout.

    Confirmed evidence -- the wallet operator says the money arrived -- but
    with no `CustomerPayment` behind it, so the key is the operator's
    transaction id ("wave:T_..."), unique like every other. With the sender's
    number the customer earns the venue's points, as at the counter.
    """
    entry = None
    points = cash_sale_points(Decimal(amount), "XOF", points_per_100) if customer_id else 0
    if points > 0:
        entry = models.LoyaltyEntry(
            customer_id=customer_id, venue_id=venue_id, points=points, reason="wallet_payment", created_at=now
        )
        db.add(entry)
        await db.flush()
    event = models.SaleEvent(
        venue_id=venue_id,
        source=CONFIRMED,
        status=RECORDED,
        amount=amount,
        currency="XOF",
        type="sale",
        occurred_at=now,
        recorded_at=now,
        customer_id=customer_id,
        loyalty_entry_id=entry.id if entry is not None else None,
        idempotency_key=idempotency_key,
        created_at=now,
    )
    db.add(event)
    return event


def record_layaway_sale(
    db: AsyncSession, *, plan: models.LayawayPlan, recorded_by: str, now: datetime
) -> models.SaleEvent:
    """The sale a layaway plan becomes when the good is handed over.

    One event for the full price, on the day of the handover: until then the
    installments are advances on a good the customer does not yet have, and a
    cancelled plan must not leave sales behind. Declared, because the merchant
    took the installments at the counter.

    No customer and no points on the event: the plan holds the number for the
    contract, but tying it to the sale history is loyalty's purpose and needs
    loyalty's consent. The key is namespaced `layaway:`, outside the `sale:`
    space clients choose from, so a client key can never collide with it.
    """
    event = models.SaleEvent(
        venue_id=plan.venue_id,
        source=DECLARED,
        status=RECORDED,
        amount=plan.price,
        currency=plan.currency,
        type="layaway",
        occurred_at=now,
        recorded_at=now,
        idempotency_key=f"layaway:{plan.id}",
        recorded_by=recorded_by,
        created_at=now,
    )
    db.add(event)
    return event


async def find_declared(db: AsyncSession, client_key: str) -> models.SaleEvent | None:
    return (
        await db.execute(
            select(models.SaleEvent).where(models.SaleEvent.idempotency_key == declared_key(client_key))
        )
    ).scalar_one_or_none()


async def record_declared_sale(
    db: AsyncSession,
    *,
    venue_id: int,
    amount: Decimal,
    currency: str,
    type_: str,
    client_key: str,
    recorded_by: str,
    occurred_at: datetime | None,
    now: datetime,
    customer_id: str | None = None,
    points_per_100: int | None = None,
) -> tuple[models.SaleEvent, bool]:
    """A cash sale the merchant recorded. Returns (event, already_existed).

    With a `customer_id` (a phone key), the customer earns the venue's points on
    the sale. The ledger entry and the event are added in the same unit of
    work, and only when the event is new: a retried key returns the original
    event and grants nothing, and two racing inserts of one key fail together
    on the event's unique key, so a sale can never pay out points twice.

    `occurred_at` is when the merchant says the sale happened, which on an
    offline queue is not when it reached us; `recorded_at` is. The gap is kept
    rather than flattened -- it is the offline window, and the statement reports
    on it.

    A key already used returns its original event untouched, which is what makes
    a retry after a dropped response safe. Whether the *contents* match is the
    caller's check (it is an HTTP conflict, not a storage concern).

    `venue_id` is an int rather than the ORM object on purpose: a batch endpoint
    rolls back between operations, which expires loaded instances, and reading an
    attribute off an expired one would attempt synchronous IO under asyncio.
    """
    existing = await find_declared(db, client_key)
    if existing is not None:
        return existing, True

    entry = None
    points = cash_sale_points(amount, currency, points_per_100) if customer_id else 0
    if points > 0:
        entry = models.LoyaltyEntry(
            customer_id=customer_id,
            venue_id=venue_id,
            points=points,
            reason="cash_sale",
            created_at=now,
        )
        db.add(entry)
        await db.flush()

    event = models.SaleEvent(
        venue_id=venue_id,
        source=DECLARED,
        status=RECORDED,
        amount=amount,
        currency=currency.upper(),
        type=type_,
        occurred_at=occurred_at or now,
        recorded_at=now,
        customer_id=customer_id,
        loyalty_entry_id=entry.id if entry is not None else None,
        idempotency_key=declared_key(client_key),
        idempotency_hash=declared_hash(
            amount=amount, currency=currency, type_=type_, occurred_at=occurred_at, customer_id=customer_id
        ),
        recorded_by=recorded_by,
        created_at=now,
    )
    db.add(event)
    return event, False


async def quarantine_summary() -> dict:
    """Count and total the quarantined backlog, for the periodic task to log.

    Migration `0014_sale_events` refused to attach these declared sales to a
    venue rather than guess. That decision is only safe if the number stays
    visible: a quarantine nobody looks at is data loss with extra steps, so the
    sweep logs it until it reaches zero.
    """
    from ..db import AsyncSessionLocal  # local: app.db imports nothing from here

    async with AsyncSessionLocal() as session:
        count, total = (
            await session.execute(
                select(
                    func.count(models.SaleEvent.id),
                    func.coalesce(func.sum(models.SaleEvent.amount), 0),
                ).where(models.SaleEvent.status == QUARANTINED)
            )
        ).one()
        return {"quarantined": int(count), "amount": str(total)}


def quarantine_summary_sync() -> dict:
    import asyncio

    return asyncio.run(quarantine_summary())
