"""Deletes sign-in and monitoring rows that no longer serve any purpose.

* `otp_challenges` older than a day. The resend cooldown and hourly cap read
  only the last hour, so anything older is dead weight holding phone numbers.
* `refresh_tokens` past their expiry, and revoked ones after 30 days. Rotated
  but unexpired tokens stay: presenting one again is how stolen-token reuse is
  detected (`app/api/auth.py`).
* `client_events` older than `CLIENT_EVENTS_RETENTION_DAYS` (default 90).
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_

from .. import models
from ..db import AsyncSessionLocal

OTP_RETENTION = timedelta(days=1)
REVOKED_RETENTION = timedelta(days=30)


def client_events_retention() -> timedelta:
    return timedelta(days=int(os.getenv("CLIENT_EVENTS_RETENTION_DAYS", "90")))


async def purge_expired(now: datetime | None = None) -> dict[str, int]:
    """Returns how many rows each table lost."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        otp = await session.execute(
            delete(models.OtpChallenge).where(models.OtpChallenge.created_at < now - OTP_RETENTION)
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
        await session.commit()
        return {
            "otp_challenges": otp.rowcount,
            "refresh_tokens": tokens.rowcount,
            "client_events": events.rowcount,
        }


def purge_expired_sync() -> dict[str, int]:
    import asyncio

    return asyncio.run(purge_expired())
