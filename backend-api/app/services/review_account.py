"""The login Apple and Google reviewers use, in Fidelia and in Fidelia Pro.

    STORE_REVIEW_PHONE     the number typed in the store forms (e.g. +2250700000077)
    STORE_REVIEW_PASSWORD  its password, a Render secret: never in the repository

Both set, every start makes sure the number has a password, a proven number
(reviewers cannot receive the team's WhatsApp code), the customer and merchant
roles, and its own sample shop to run in Fidelia Pro. Unlike the sample data
(app/seed.py) this is allowed in production, where the store builds point:
the shop holds no wallet, so no real money can reach it, and it is kept out of
the public catalogue (`public_venue_filter`) so customers never see it.

Changing STORE_REVIEW_PASSWORD on Render and restarting replaces the password.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import select

from .. import models
from ..core import passwords
from ..core.phone import InvalidPhone, normalize_phone, phone_key
from ..db import AsyncSessionLocal

SHOP_NAME = "Maquis Demo Fidelia (exemple)"
_ROLES = {"customer", "merchant"}
_REWARDS = [("Boisson offerte", 50), ("Plat offert", 150)]


def env_login(phone_var: str, password_var: str) -> str | None:
    """A login configured by a pair of environment variables: the number in
    E.164, or None when neither is set. Half a setup, or a weak password,
    stops the start rather than leaving someone locked out unnoticed."""
    phone = os.getenv(phone_var, "").strip()
    password = os.getenv(password_var, "")
    if not phone and not password:
        return None
    if not phone or not password:
        raise RuntimeError(f"{phone_var} and {password_var} are set together, or not at all")
    try:
        passwords.check_rules(password)
    except ValueError as exc:
        raise RuntimeError(f"{password_var}: {exc}") from exc
    try:
        return normalize_phone(phone, "CI")
    except InvalidPhone as exc:
        raise RuntimeError(f"{phone_var}: {exc}") from exc


def ensure_login(user: models.User | None, phone: str, password: str, roles: set[str], now: datetime) -> models.User:
    """Gives `phone` the roles, the password (replaced when it changed), a
    proven number and a clean slate: unlocked, not suspended."""
    if user is None:
        user = models.User(phone_e164=phone, roles="", disabled=False, created_at=now)
    user.roles = ",".join(sorted(user.role_set() | roles))
    if not user.password_hash or not passwords.verify_password(password, user.password_hash):
        user.password_hash = passwords.hash_password(password)
    user.phone_verified_at = user.phone_verified_at or now
    user.must_change_password = False
    user.disabled = False
    user.failed_logins = 0
    user.locked_until = None
    return user


def review_phone() -> str | None:
    """The review number in E.164, or None when the account is not set up."""
    return env_login("STORE_REVIEW_PHONE", "STORE_REVIEW_PASSWORD")


def public_venue_filter() -> tuple:
    """Conditions that keep the review shop out of public listings."""
    phone = review_phone()
    if phone is None:
        return ()
    owner = models.Venue.owner_username
    return (owner.is_(None) | (owner != phone_key(phone)),)


async def ensure_review_account() -> None:
    phone = review_phone()
    if phone is None:
        return
    password = os.environ["STORE_REVIEW_PASSWORD"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == phone))).scalar_one_or_none()
        db.add(ensure_login(user, phone, password, _ROLES, now))

        owner = phone_key(phone)
        shop = (await db.execute(select(models.Venue).where(models.Venue.owner_username == owner))).scalars().first()
        if shop is None:
            shop = models.Venue(
                category="maquis",
                name=SHOP_NAME,
                commune="Cocody",
                address="Etablissement fictif pour la revue des stores",
                specialties="Poulet braise, attieke poisson",
                opening_hours="12h - 23h",
                description="Etablissement fictif, donnees de demonstration.",
                points_per_100=2,
                owner_username=owner,
                is_sample=True,
            )
            shop.rewards = [models.LoyaltyReward(title=t, cost_points=c) for t, c in _REWARDS]
            db.add(shop)
        await db.commit()
