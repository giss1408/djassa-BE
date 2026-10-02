"""Error reports from our own apps, instead of a third-party crash SDK.

The apps catch their uncaught errors, keep them in a small local queue, and
send them here in one batch at start-up or when they come back to the
foreground (djassa-App-*/lib/core/monitoring/). The web site sends its own
with `navigator.sendBeacon`. Every report increments a Prometheus counter, so
Grafana and Alertmanager see a crash spike the way they see a 5xx spike; the
rows keep the stack traces for whoever fixes it.

Unauthenticated on purpose: the crash worth knowing about is often the one
that happens before sign-in. Bounded on purpose too: 20 events per call, short
fields, IP rate limit, and digit runs (in messages) and tokens (everywhere)
scrubbed again here in case a client forgot.

Release APKs are built with --obfuscate, so their stacks are addresses. Read
one with `flutter symbolize -i <stack file> -d build/symbols/app.android-arm.symbols`
against the symbols archived for that `app_version`.
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.security import require_role
from ..db import get_db
from ..metrics import CLIENT_EVENTS
from ..rate_limiter import limiter

router = APIRouter()

AppName = Literal["user", "retailer", "web"]
Platform = Literal["android", "ios", "web", "other"]


class ClientEventIn(BaseModel):
    kind: Literal["crash", "error"] = "error"
    message: str = Field(min_length=1, max_length=2000)
    stack: str | None = Field(default=None, max_length=20000)
    count: int = Field(default=1, ge=1, le=10000)
    occurred_at: datetime


class ClientEventBatchIn(BaseModel):
    app: AppName
    # Bounded format, because it becomes a Prometheus label.
    app_version: str = Field(pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,4}(\+\d{1,6})?$")
    platform: Platform
    os_version: str | None = Field(default=None, max_length=64)
    events: list[ClientEventIn] = Field(min_length=1, max_length=20)


class ClientEventGroupOut(BaseModel):
    fingerprint: str
    app: str
    kind: str
    message: str
    occurrences: int
    reports: int
    first_seen: datetime
    last_seen: datetime
    latest_version: str
    stack: str | None


_DIGITS = re.compile(r"\+?\d[\d ]{3,}\d")
_BEARER = re.compile(r"(?i)bearer\s+[\w\-.~+/]+=*")
_JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
# Frame noise that changes between runs or builds but not between occurrences
# of one bug: source positions, frame numbers, and the absolute (ASLR) address
# of an obfuscated frame. The `virt` offset stays: it is what identifies it.
_VOLATILE = re.compile(r":\d+(:\d+)?\)?|^#\d+\s+|abs [0-9a-f]+\s*|0x[0-9a-f]+")


def scrub_tokens(text: str | None) -> str | None:
    """For stacks: frames carry no values, and release builds are obfuscated
    into hex addresses that `flutter symbolize` needs intact."""
    if text is None:
        return None
    return _BEARER.sub("Bearer <token>", _JWT.sub("<token>", text))


def scrub(text: str | None) -> str | None:
    """Phone numbers, amounts, account numbers and tokens never get stored.

    Any run of 5+ digits goes: that covers phones and amounts while leaving
    stack line numbers (`file.dart:42:7`) readable."""
    if text is None:
        return None
    text = _JWT.sub("<token>", text)
    text = _BEARER.sub("Bearer <token>", text)
    return _DIGITS.sub("<num>", text)


def fingerprint(app: str, kind: str, message: str, stack: str | None) -> str:
    # The top frames identify the bug; the message alone often carries ids.
    # Only "#n ..." lines are frames: an obfuscated trace opens with header
    # lines (pid, build_id) that every error of a build shares.
    frames = [line.strip() for line in (stack or "").splitlines() if line.strip().startswith("#")][:5]
    basis = "\n".join(_VOLATILE.sub("", frame) for frame in frames) if frames else re.sub(r"\d+", "#", message)[:200]
    return hashlib.sha256(f"{app}|{kind}|{basis}".encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


@router.post("/client-events", status_code=202)
@limiter.limit("30/minute")
async def report(request: Request, payload: ClientEventBatchIn, db: AsyncSession = Depends(get_db)):
    now = utcnow()
    for event in payload.events:
        message = scrub(event.message)[:512]
        stack = scrub_tokens(event.stack)
        occurred = _naive_utc(event.occurred_at)
        # A device clock years off is common on old phones; trust our clock then.
        if abs(occurred - now) > timedelta(days=30):
            occurred = now
        db.add(
            models.ClientEvent(
                app=payload.app, app_version=payload.app_version, platform=payload.platform,
                os_version=scrub(payload.os_version), kind=event.kind,
                fingerprint=fingerprint(payload.app, event.kind, message, stack),
                message=message, stack=stack[:8000] if stack else None, count=event.count,
                occurred_at=occurred, received_at=now,
            )
        )
        CLIENT_EVENTS.labels(
            app=payload.app, platform=payload.platform, kind=event.kind, app_version=payload.app_version
        ).inc(event.count)
    await db.commit()
    return {"accepted": len(payload.events)}


@router.get("/admin/client-events", response_model=list[ClientEventGroupOut])
async def list_groups(
    app: AppName | None = None,
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("admin")),
):
    """One line per bug, most frequent first."""
    E = models.ClientEvent
    query = (
        select(
            E.fingerprint, E.app, E.kind,
            func.sum(E.count).label("occurrences"), func.count(E.id).label("reports"),
            func.min(E.occurred_at).label("first_seen"), func.max(E.occurred_at).label("last_seen"),
            func.max(E.id).label("latest_id"),
        )
        .where(E.received_at >= utcnow() - timedelta(days=days))
        .group_by(E.fingerprint, E.app, E.kind)
        .order_by(func.sum(E.count).desc())
        .limit(100)
    )
    if app is not None:
        query = query.where(E.app == app)
    groups = (await db.execute(query)).all()
    latest = {
        row.id: row
        for row in (await db.execute(select(E).where(E.id.in_([g.latest_id for g in groups])))).scalars()
    }
    return [
        ClientEventGroupOut(
            fingerprint=g.fingerprint, app=g.app, kind=g.kind, message=latest[g.latest_id].message,
            occurrences=g.occurrences, reports=g.reports, first_seen=g.first_seen, last_seen=g.last_seen,
            latest_version=latest[g.latest_id].app_version, stack=latest[g.latest_id].stack,
        )
        for g in groups
    ]
