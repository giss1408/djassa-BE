"""Telling the auth service a person was erased, with a retry.

Fidelia deletes its own data first and commits. Then `tell_auth` calls the auth service; when it cannot be reached the person goes into an
outbox (her number sealed at rest) and `process_outbox` (a periodic task, `auth.erase_outbox`) retries with a growing delay until auth
answers. Done rows lose the number at once; a row still failing after AUTH_ERASE_MAX_DAYS (default 30) is given up, blanked, and logged for
a person to look at (the number is the only way to find her in auth, and fidelia must not keep it forever).
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core import secretbox, sso
from ..db import AsyncSessionLocal

log = logging.getLogger("fidelia.auth_erase")

DONE_RETENTION = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def max_age() -> timedelta:
    return timedelta(days=int(os.getenv("AUTH_ERASE_MAX_DAYS", "30")))


def _delay(attempts: int) -> timedelta:
    """1 min, 2, 4... capped at 6 hours."""
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), 360))


async def tell_auth(phone_e164: str) -> None:
    """Right after fidelia's data is gone. Never raises: the deletion stands whatever auth does."""
    try:
        outcome = await sso.erase_identity(phone_e164)
        if outcome is False:
            now = _now()
            async with AsyncSessionLocal() as db:
                db.add(models.AuthEraseOutbox(phone_sealed=secretbox.seal(phone_e164), created_at=now, attempts=1, next_attempt_at=now + _delay(1)))
                await db.commit()
    except Exception:  # never let a bookkeeping failure undo or hide a deletion
        log.error("auth erase could not even be queued: the person is deleted in fidelia but her auth identity remains", exc_info=False)


async def process_outbox(now: datetime | None = None, *, limit: int = 50) -> dict[str, int]:
    """Retries what is due. Returns counts only (no numbers)."""
    now = now or _now()
    out = {"done": 0, "retry": 0, "gave_up": 0, "purged": 0}
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(models.AuthEraseOutbox)
                .where(models.AuthEraseOutbox.status == "pending", models.AuthEraseOutbox.next_attempt_at <= now)
                .order_by(models.AuthEraseOutbox.id)
                .limit(limit)
            )
        ).all()
        for row in rows:
            try:
                phone = secretbox.unseal(row.phone_sealed)
            except secretbox.SecretUnavailable:
                phone = None
            outcome = await sso.erase_identity(phone) if phone else None
            if outcome is True or outcome is None and phone is not None:
                # answered; or SSO switched off meanwhile: nothing left to tell
                row.status, row.phone_sealed, row.finished_at = "done", "", now
                out["done"] += 1
            elif phone is None or now - row.created_at > max_age():
                log.error("auth erase GIVEN UP (outbox id %s): erase her auth identity by hand", row.id)
                row.status, row.phone_sealed, row.finished_at = "gave_up", "", now
                out["gave_up"] += 1
            else:
                row.attempts += 1
                row.next_attempt_at = now + _delay(row.attempts)
                out["retry"] += 1
        purged = await db.execute(
            delete(models.AuthEraseOutbox).where(models.AuthEraseOutbox.status != "pending", models.AuthEraseOutbox.finished_at < now - DONE_RETENTION)
        )
        out["purged"] = purged.rowcount or 0
        await db.commit()
    return out


def process_outbox_sync() -> dict[str, int]:
    import asyncio

    return asyncio.run(process_outbox())
