"""Account checks the team sends by hand on WhatsApp.

A check is opened (`pending`), sent by an admin (`sent`, with a fresh code or
temporary password valid for 24 h) and then done or refused. Only an HMAC of
the secret is stored. Callers commit, except that a wrong code is committed
here so the attempt counts even though the request fails.
"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.tokens import hmac_secret, secret_matches
from .whatsapp import whatsapp_link

VALID_FOR = timedelta(hours=24)
MAX_ATTEMPTS = 5
PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
PASSWORD_LENGTH = 10
OPEN_STATUSES = ("pending", "sent")


class BadCode(Exception):
    """The code is wrong, expired, or no code is waiting."""


def _code_text(code: str) -> str:
    spaced = f"{code[:3]} {code[3:]}"
    return (
        f"Bonjour, voici votre code Fidelia : {spaced}. "
        "Saisissez-le dans l'application. Valable 24 h. Ne le partagez avec personne."
    )


def _password_text(password: str) -> str:
    return (
        f"Bonjour, votre mot de passe temporaire Fidelia : {password}. "
        "Vous devrez en choisir un nouveau a la connexion."
    )


async def open_check(
    db: AsyncSession,
    user: models.User,
    kind: str,
    now: datetime,
    new_phone_e164: str | None = None,
    team_created: bool = False,
) -> models.AccountCheck:
    check = (
        await db.execute(
            select(models.AccountCheck)
            .where(
                models.AccountCheck.user_id == user.id,
                models.AccountCheck.kind == kind,
                models.AccountCheck.status.in_(OPEN_STATUSES),
            )
            .order_by(models.AccountCheck.id.desc())
        )
    ).scalars().first()
    if check is None:
        check = models.AccountCheck(
            user_id=user.id, kind=kind, status="pending", attempts=0, created_at=now, team_created=team_created
        )
        db.add(check)
    if new_phone_e164 is not None:
        if check.new_phone_e164 not in (None, new_phone_e164):
            # A code already sent went to the earlier number: it must not
            # confirm a move to this one.
            check.status = "pending"
            check.secret_hash = None
        check.new_phone_e164 = new_phone_e164
    await db.flush()
    return check


async def send_check(db: AsyncSession, check: models.AccountCheck, admin_user_id: int, now: datetime) -> str:
    """Makes a new secret (the previous one stops working) and returns the
    WhatsApp link carrying it."""
    user = await db.get(models.User, check.user_id)
    if check.kind == "reset_password":
        secret = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))
        message = _password_text(secret)
    else:
        secret = f"{secrets.randbelow(1_000_000):06d}"
        message = _code_text(secret)
    phone = check.new_phone_e164 if check.kind == "change_number" else user.phone_e164
    check.secret_hash = hmac_secret(check.user_id, check.kind, secret)
    check.status = "sent"
    check.attempts = 0
    check.sent_by = str(admin_user_id)
    check.sent_at = now
    check.expires_at = now + VALID_FOR
    await db.flush()
    return whatsapp_link(phone, message)


async def verify_code(db: AsyncSession, user: models.User, kind: str, code: str, now: datetime) -> models.AccountCheck:
    check = (
        await db.execute(
            select(models.AccountCheck)
            .where(
                models.AccountCheck.user_id == user.id,
                models.AccountCheck.kind == kind,
                models.AccountCheck.status == "sent",
            )
            .order_by(models.AccountCheck.id.desc())
        )
    ).scalars().first()
    if check is None or check.secret_hash is None or check.expires_at is None or check.expires_at <= now:
        raise BadCode()
    check.attempts += 1
    if not secret_matches(user.id, kind, code, check.secret_hash):
        if check.attempts >= MAX_ATTEMPTS:
            check.status = "pending"
            check.secret_hash = None
        await db.commit()
        raise BadCode()
    check.status = "done"
    check.done_at = now
    return check


async def use_temporary_password(db: AsyncSession, user: models.User, password: str, now: datetime) -> bool:
    check = (
        await db.execute(
            select(models.AccountCheck)
            .where(
                models.AccountCheck.user_id == user.id,
                models.AccountCheck.kind == "reset_password",
                models.AccountCheck.status == "sent",
            )
            .order_by(models.AccountCheck.id.desc())
        )
    ).scalars().first()
    if check is None or check.secret_hash is None or check.expires_at is None or check.expires_at <= now:
        return False
    if not secret_matches(user.id, "reset_password", password, check.secret_hash):
        return False
    check.status = "done"
    check.done_at = now
    return True


async def refuse(db: AsyncSession, check: models.AccountCheck, now: datetime) -> None:
    check.status = "refused"
    check.done_at = now
    check.secret_hash = None
