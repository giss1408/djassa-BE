"""The super admin: the one login set from Render, so the team never starts
locked out of Fidelia Admin.

    FIDELIA_SUPER_ADMIN_PHONE     the number (e.g. +2250700000010)
    FIDELIA_SUPER_ADMIN_PASSWORD  its password, a Render secret: never in the repository

Both set, every start gives that number the `admin` and `superadmin` roles,
the password and a proven number. Changing the secret and restarting
replaces the password, which is also how a forgotten one is recovered.

A super admin is an admin who may also do what must not be in every admin's
hands; today, setting the shared test logins' password
(`/api/admin/accounts/test-accounts/password`). The `superadmin` role is read
from the database on each call, not from the token.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import select

from .. import models
from ..db import AsyncSessionLocal
from .review_account import ensure_login, env_login

ROLE = "superadmin"


def super_admin_phone() -> str | None:
    return env_login("FIDELIA_SUPER_ADMIN_PHONE", "FIDELIA_SUPER_ADMIN_PASSWORD")


async def ensure_super_admin() -> None:
    phone = super_admin_phone()
    if phone is None:
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == phone))).scalar_one_or_none()
        db.add(ensure_login(user, phone, os.environ["FIDELIA_SUPER_ADMIN_PASSWORD"], {"admin", ROLE}, now))
        await db.commit()
