"""Spent codes, dead sessions and old error reports are deleted; live ones stay."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.services.purge import purge_expired


@pytest.mark.asyncio
async def test_purge_keeps_what_is_still_useful():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    now = datetime(2026, 10, 2, 12, 0)

    async with AsyncSessionLocal() as db:
        user = models.User(phone_e164="+2250712345678", roles="customer", disabled=False, created_at=now)
        db.add(user)
        await db.flush()

        def code(age):
            return models.OtpChallenge(
                phone_e164=user.phone_e164, code_hash="x" * 64, attempts=0,
                expires_at=now - age + timedelta(minutes=5), created_at=now - age,
            )

        def token(name, expires_in, revoked_ago=None, rotated=False):
            return models.RefreshToken(
                user_id=user.id, token_hash=name.ljust(64, "0"), family="f", role="customer",
                expires_at=now + expires_in, created_at=now - timedelta(days=1),
                revoked_at=now - revoked_ago if revoked_ago else None,
                rotated_at=now - timedelta(days=1) if rotated else None,
            )

        def event(age):
            return models.ClientEvent(
                app="user", app_version="0.1.0+1", platform="android", kind="error",
                fingerprint="f", message="m", count=1, occurred_at=now - age, received_at=now - age,
            )

        db.add_all([
            code(timedelta(hours=2)),
            code(timedelta(days=2)),
            token("live", timedelta(days=10)),
            # Rotated but unexpired: kept, it is what detects a stolen token.
            token("rotated", timedelta(days=10), rotated=True),
            token("expired", timedelta(days=-1)),
            token("revokedrecent", timedelta(days=10), revoked_ago=timedelta(days=5)),
            token("revokedold", timedelta(days=10), revoked_ago=timedelta(days=40)),
            event(timedelta(days=10)),
            event(timedelta(days=100)),
        ])
        await db.commit()

    assert await purge_expired(now) == {"otp_challenges": 1, "refresh_tokens": 2, "client_events": 1, "usage_events": 0}

    async with AsyncSessionLocal() as db:
        left = {t.token_hash.rstrip("0") for t in (await db.execute(select(models.RefreshToken))).scalars()}
        codes = (await db.execute(select(models.OtpChallenge))).scalars().all()
        events = (await db.execute(select(models.ClientEvent))).scalars().all()
    assert left == {"live", "rotated", "revokedrecent"}
    assert len(codes) == 1 and len(events) == 1


@pytest.mark.asyncio
async def test_retention_is_configurable(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    now = datetime(2026, 10, 2, 12, 0)
    async with AsyncSessionLocal() as db:
        db.add(models.ClientEvent(
            app="web", app_version="0.0.0", platform="web", kind="error", fingerprint="f",
            message="m", count=1, occurred_at=now - timedelta(days=10), received_at=now - timedelta(days=10),
        ))
        await db.commit()
    monkeypatch.setenv("CLIENT_EVENTS_RETENTION_DAYS", "7")
    assert (await purge_expired(now))["client_events"] == 1
