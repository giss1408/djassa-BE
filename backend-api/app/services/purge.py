"""Deletes sign-in and monitoring rows that no longer serve any purpose.

* `account_checks` the team has finished (done or refused) more than 30 days
  ago: each row holds a phone number's check and the hashed secret sent.
* `refresh_tokens` past their expiry, and revoked ones after 30 days. Rotated
  but unexpired tokens stay: presenting one again is how stolen-token reuse is
  detected (`app/api/auth.py`).
* `client_events` older than `CLIENT_EVENTS_RETENTION_DAYS` (default 90).
* `usage_events` older than `USAGE_EVENTS_RETENTION_DAYS` (default 400: the
  pilot compares retention at 30/60/90 days and a full year of seasons).
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_

from .. import models
from ..db import AsyncSessionLocal

CHECKS_RETENTION = timedelta(days=30)
REVOKED_RETENTION = timedelta(days=30)


def client_events_retention() -> timedelta:
    return timedelta(days=int(os.getenv("CLIENT_EVENTS_RETENTION_DAYS", "90")))


def usage_events_retention() -> timedelta:
    return timedelta(days=int(os.getenv("USAGE_EVENTS_RETENTION_DAYS", "400")))


async def purge_expired(now: datetime | None = None) -> dict[str, int]:
    """Returns how many rows each table lost."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        checks = await session.execute(
            delete(models.AccountCheck).where(
                models.AccountCheck.status.in_(("done", "refused")),
                models.AccountCheck.done_at < now - CHECKS_RETENTION,
            )
        )
        tokens = await session.execute(
            delete(models.RefreshToken).where(
                or_(
                    models.RefreshToken.expires_at < now,
                    models.RefreshToken.revoked_at < now - REVOKED_RETENTION,
                )
            )
        )
        events = await session.execute(
            delete(models.ClientEvent).where(models.ClientEvent.received_at < now - client_events_retention())
        )
        usage = await session.execute(
            delete(models.UsageEvent).where(models.UsageEvent.received_at < now - usage_events_retention())
        )
        await session.commit()
        return {
            "account_checks": checks.rowcount,
            "refresh_tokens": tokens.rowcount,
            "client_events": events.rowcount,
            "usage_events": usage.rowcount,
        }


def purge_expired_sync() -> dict[str, int]:
    import asyncio

    return asyncio.run(purge_expired())
