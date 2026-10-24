"""Shared test helpers for password sign-in."""

import re
import secrets
from datetime import datetime, timezone
from urllib.parse import unquote

from sqlalchemy import select

from app import models
from app.core.passwords import hash_password
from app.core.phone import normalize_phone
from app.db import AsyncSessionLocal
from app.services import account_checks

# Generated per run, so no password literal sits in the repository (secret
# scanners flag them) and no test depends on a particular value.
TEST_PASSWORD = secrets.token_urlsafe(12)
OTHER_PASSWORD = secrets.token_urlsafe(12)
WRONG_PASSWORD = secrets.token_urlsafe(12)
SQUATTER_PASSWORD = secrets.token_urlsafe(12)


async def make_user(phone, roles="customer", password=TEST_PASSWORD, verified=True) -> None:
    """Writes a user straight to the database. `phone` is in national form."""
    e164 = normalize_phone(phone, "CI")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        db.add(
            models.User(
                phone_e164=e164, roles=roles, disabled=False, created_at=now,
                password_hash=hash_password(password) if password else None,
                phone_verified_at=now if verified else None,
            )
        )
        await db.commit()


async def sign_in(ac, phone, app="customer", password=TEST_PASSWORD):
    return await ac.post("/api/auth/login", json={"phone": phone, "country_code": "CI", "password": password, "app": app})


async def phone_session(ac, phone, app="customer"):
    """Signs `phone` in to `app`, the way the old code flow did: a number the
    database has never seen becomes a verified customer first; a seeded
    account signs in with the seed password."""
    e164 = normalize_phone(phone, "CI")
    async with AsyncSessionLocal() as db:
        known = (await db.execute(select(models.User.id).where(models.User.phone_e164 == e164))).first()
    if known is None:
        await make_user(phone)
    from app.seed import DEV_ACCOUNTS, dev_password

    if e164 in {seeded for seeded, _ in DEV_ACCOUNTS}:
        return await sign_in(ac, phone, app=app, password=dev_password())
    return await sign_in(ac, phone, app=app)
    return r


async def arm(phone, password=TEST_PASSWORD) -> None:
    """Gives an existing user (a seeded one, or one a team action created) a
    password and a proven number, so it can sign in."""
    e164 = normalize_phone(phone, "CI")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one()
        user.password_hash = hash_password(password)
        user.phone_verified_at = now
        user.must_change_password = False
        await db.commit()


async def send_open_check(phone, kind) -> str:
    """What the admin app does: sends the user's open check and returns the
    code (or temporary password) carried by the WhatsApp link."""
    e164 = normalize_phone(phone, "CI")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one()
        check = (
            await db.execute(
                select(models.AccountCheck).where(
                    models.AccountCheck.user_id == user.id,
                    models.AccountCheck.kind == kind,
                    models.AccountCheck.status.in_(("pending", "sent")),
                )
            )
        ).scalars().first()
        link = await account_checks.send_check(db, check, 1, now)
        await db.commit()
    text = unquote(link).replace("+", " ")
    match = re.search(r"code Fidelia : (\d{3} \d{3})\.|temporaire Fidelia : (\S+?)\. ", text)
    return match.group(1).replace(" ", "") if match.group(1) else match.group(2)


# --- Fixed-credential test accounts -------------------------------------------

# The old POST /api/token demo accounts are gone from the API. Tests that only
# need "a merchant who owns the first sample maquis", "a customer" or "an admin"
# mint the same tokens here, without a route that could ship.
_DEMO_ACCOUNTS = {
    "demo": ("demo123", "merchant"),
    "client": ("client123", "customer"),
    "admin": ("admin123", "admin"),
}


class _TokenResponse:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body
        self.text = str(body)

    def json(self):
        return self._body


async def demo_login(ac, data):
    """Stands in for the removed POST /api/token: same arguments, same answer."""
    from app.core import security

    password, role = _DEMO_ACCOUNTS.get(data["username"], (None, None))
    if password is None or data["password"] != password:
        return _TokenResponse(401, {"detail": "Incorrect username or password"})
    token = security.create_access_token({"sub": data["username"], "role": role})
    return _TokenResponse(200, {"access_token": token, "token_type": "bearer", "role": role})
