"""Shared test helpers for password sign-in."""

import re
from datetime import datetime, timezone
from urllib.parse import unquote

from sqlalchemy import select

from app import models
from app.core.passwords import hash_password
from app.core.phone import normalize_phone
from app.db import AsyncSessionLocal
from app.services import account_checks


async def make_user(phone, roles="customer", password="motdepasse1", verified=True) -> None:
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


async def sign_in(ac, phone, app="customer", password="motdepasse1"):
    return await ac.post("/api/auth/login", json={"phone": phone, "country_code": "CI", "password": password, "app": app})


async def arm(phone, password="motdepasse1") -> None:
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
