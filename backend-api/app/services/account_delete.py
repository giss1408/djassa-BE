"""Deletes a customer's account (Google Play's account deletion requirement).

What identifies the person is erased; what is the merchants' business record
stays, under a random key that names nobody:

* erased: points and the loyalty consent, the identity profile, consents,
  support requests, sign-in codes, recovery and number-change history,
  sessions, and the account itself;
* kept anonymous: payments, sales, closed layaway plans and tontine records,
  re-keyed to `deleted:<random>` (payer numbers blanked), so a shop's history
  and totals do not change.

A merchant or cashier cannot delete themselves: the shop's records and its
staff are decided by the team (`AccountDeletionRequest`), which deletes the
account with `staff=True` once the person owns no shop. Their name in the
shop's history ("recorded by", "added by", account_move.AUDIT) is re-keyed to
the tombstone too. Every column in account_move.OWNED is classified below, and
tests/test_account_delete.py fails on a new one that is not, so a new table
cannot keep a deleted person.
"""

import secrets
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.phone import phone_key
from . import loyalty_consent
from .account_move import AUDIT, OWNED

# Rows that are only about the person: deleted.
ERASE = [
    (models.Consent, "user_id"),
    (models.SupportRequest, "user_id"),
    (models.IdentityProfile, "user_id"),
    (models.LoyaltyEntry, "customer_id"),
    (models.LoyaltyConsent, "customer_id"),
]

# Rows that are also someone else's record: kept, re-keyed to a tombstone.
ANONYMIZE = [
    (models.Payment, "created_by"),
    (models.Transaction, "user_id"),
    (models.TontineGroup, "organizer_id"),
    (models.TontineMember, "user_id"),
    (models.CustomerPayment, "customer_id"),
    (models.SaleEvent, "customer_id"),
    (models.LayawayPlan, "customer_id"),
]

# A person holding one of these is staff: refused, they ask the team.
MERCHANT = [
    (models.Venue, "owner_username"),
    (models.Venue, "enrolled_by"),
    (models.VenueStaff, "user_key"),
]

OPEN_LAYAWAY = ("open", "completed")


class OwnsShop(Exception):
    """The account still owns a shop: close it or hand it over first."""


class IsShopStaff(Exception):
    """The account runs or works in a shop: deletion goes through the team."""


class LayawayInProgress(Exception):
    """A layaway plan is not finished: the money is with a merchant."""


async def is_shop_staff(db: AsyncSession, key: str) -> bool:
    for model, column in MERCHANT:
        query = select(model).where(getattr(model, column) == key)
        if model is models.VenueStaff:
            query = query.where(models.VenueStaff.removed_at.is_(None))
        if (await db.execute(query.limit(1))).first() is not None:
            return True
    return False


async def delete_account(
    db: AsyncSession, user: models.User, now: datetime, *, staff: bool = False, decided_by: str | None = None
) -> None:
    """Erases or anonymizes everything tied to `user`, then the user. The caller commits.

    `staff=False` is the customer's own deletion: refused for anyone with a
    staff role or a shop. `staff=True` is an admin acting on a deletion
    request: refused while the person owns a shop; their cashier places end."""
    e164 = user.phone_e164
    key = phone_key(e164)
    roles = user.role_set()
    if not staff and (roles & {"merchant", "admin", "agent", "cashier"} or await is_shop_staff(db, key)):
        raise IsShopStaff()
    if staff:
        owned = await db.execute(select(models.Venue.id).where(models.Venue.owner_username == key).limit(1))
        if owned.first() is not None:
            raise OwnsShop()
        await db.execute(
            update(models.VenueStaff)
            .where(models.VenueStaff.user_key == key, models.VenueStaff.removed_at.is_(None))
            .values(removed_at=now, removed_by=decided_by)
        )
    open_plan = await db.execute(
        select(models.LayawayPlan.id)
        .where(models.LayawayPlan.customer_id == key, models.LayawayPlan.status.in_(OPEN_LAYAWAY))
        .limit(1)
    )
    if open_plan.first() is not None:
        raise LayawayInProgress()

    # Points first: this also unlinks the sales that earned them.
    await loyalty_consent.withdraw(db, key, now)

    for model, column in ERASE:
        await db.execute(delete(model).where(getattr(model, column) == key))
    tombstone = "deleted:" + secrets.token_hex(8)
    for model, column in ANONYMIZE + AUDIT + [(models.VenueStaff, "user_key"), (models.Venue, "enrolled_by")]:
        await db.execute(update(model).where(getattr(model, column) == key).values({column: tombstone}))
    await db.execute(
        update(models.CustomerPayment).where(models.CustomerPayment.customer_id == tombstone).values(payer_msisdn="")
    )

    await db.execute(delete(models.OtpChallenge).where(models.OtpChallenge.phone_e164 == e164))
    await db.execute(
        delete(models.RecoveryRequest).where(
            or_(models.RecoveryRequest.old_phone_e164 == e164, models.RecoveryRequest.new_phone_e164 == e164)
        )
    )
    await db.execute(delete(models.AccountNumberChange).where(models.AccountNumberChange.user_id == user.id))
    await db.execute(delete(models.RefreshToken).where(models.RefreshToken.user_id == user.id))
    await db.delete(user)


def unclassified() -> list[tuple[str, str]]:
    """OWNED columns this module does not know what to do with (must be empty)."""
    known = {(m.__name__, c) for m, c in ERASE + ANONYMIZE + MERCHANT}
    return [(m.__name__, c) for m, c in OWNED if (m.__name__, c) not in known]
