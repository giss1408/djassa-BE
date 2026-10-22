"""Shared test helpers for password sign-in."""

from datetime import datetime, timezone

from app import models
from app.core.passwords import hash_password
from app.core.phone import normalize_phone
from app.db import AsyncSessionLocal


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
