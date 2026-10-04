"""Moves an account from one phone number to another.

The token subject is `tel:+225...` (`app/core/phone.py`), and the tables
store that key rather than `users.id`, so a number change re-keys every column
that says "this belongs to that person". Audit columns that say "this person
did that, back then" keep the old key: history is not rewritten.

Every column holding a subject must be listed in OWNED or AUDIT;
tests/test_account_recovery.py fails on any 128-character string column that
is in neither, so a new table cannot silently stay behind on the old number.
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.phone import phone_key

# Follow the person to the new number.
OWNED = [
    (models.Payment, "created_by"),
    (models.Transaction, "user_id"),
    (models.Consent, "user_id"),
    (models.TontineGroup, "organizer_id"),
    (models.TontineMember, "user_id"),
    (models.CustomerPayment, "customer_id"),
    (models.LoyaltyEntry, "customer_id"),
    (models.SupportRequest, "user_id"),
    (models.IdentityProfile, "user_id"),
    (models.SaleEvent, "customer_id"),
    (models.Venue, "owner_username"),
    (models.Venue, "enrolled_by"),
    (models.VenueStaff, "user_key"),
]

# Who did something, as it was at the time. Left on the old key.
AUDIT = [
    (models.ExportAudit, "exported_by"),
    (models.DealPlacement, "created_by"),
    (models.WaveAccount, "connected_by"),
    (models.BillingEvent, "recorded_by"),
    (models.SaleEvent, "recorded_by"),
    (models.RecoveryRequest, "decided_by"),
    (models.PartnerRequest, "decided_by"),
    (models.VenueMedia, "uploaded_by"),
    (models.VenueStaff, "added_by"),
    (models.VenueStaff, "removed_by"),
]


class NumberTaken(Exception):
    """The new number already has an account. Two accounts are never merged
    automatically: each may hold points, a shop, or an identity profile."""


async def move_account(
    db: AsyncSession,
    user: models.User,
    new_e164: str,
    *,
    method: str,
    now: datetime,
    recovery_request_id: int | None = None,
) -> None:
    """Re-keys `user` to `new_e164` and ends all its sessions. The caller commits."""
    taken = (await db.execute(select(models.User.id).where(models.User.phone_e164 == new_e164))).scalar_one_or_none()
    if taken is not None:
        raise NumberTaken()

    old_e164 = user.phone_e164
    old_key, new_key = phone_key(old_e164), phone_key(new_e164)
    for model, column in OWNED:
        attr = getattr(model, column)
        await db.execute(update(model).where(attr == old_key).values({column: new_key}))
    await db.execute(
        update(models.IdentityProfile).where(models.IdentityProfile.user_id == new_key).values(phone_e164=new_e164)
    )

    user.phone_e164 = new_e164
    # Whoever holds the old number, or a session opened on it, is out.
    await revoke_all_sessions(db, user.id, now)
    db.add(
        models.AccountNumberChange(
            user_id=user.id, old_phone_e164=old_e164, new_phone_e164=new_e164,
            method=method, recovery_request_id=recovery_request_id, created_at=now,
        )
    )


async def revoke_all_sessions(db: AsyncSession, user_id: int, now: datetime, keep_token_hash: str | None = None) -> int:
    """Revokes every refresh token of the user, except one family if asked."""
    query = update(models.RefreshToken).where(
        models.RefreshToken.user_id == user_id, models.RefreshToken.revoked_at.is_(None)
    )
    if keep_token_hash is not None:
        kept = (
            await db.execute(select(models.RefreshToken.family).where(models.RefreshToken.token_hash == keep_token_hash))
        ).scalar_one_or_none()
        if kept is not None:
            query = query.where(models.RefreshToken.family != kept)
    result = await db.execute(query.values(revoked_at=now))
    return result.rowcount


async def revoke_role_sessions(db: AsyncSession, user_id: int, role: str, now: datetime) -> int:
    """Revokes the user's refresh tokens for one role, e.g. a removed cashier."""
    result = await db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.user_id == user_id, models.RefreshToken.role == role, models.RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return result.rowcount
