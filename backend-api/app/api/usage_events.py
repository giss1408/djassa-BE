"""App usage for the pilot: installs, active users, screens and content seen.

Our own pipeline instead of an analytics SDK, for the same reasons as
`client_events`: merchants and customers pay for every byte, and nothing
leaves for a third party. The apps keep a small aggregated queue and send it
in one request at start-up or when they come back to the foreground
(djassa-App-*/lib/core/monitoring/usage_tracker.dart).

Identity, deliberately minimal:

* every row carries an **install id**: a random string the app creates on
  first launch and keeps in its own storage. Not a device id, not a phone
  number. It is what makes "how many installs" and "how many active this
  week" countable;
* the **merchant app** attaches the shop (`venue_id`) when the merchant is
  signed in, because the pilot is measured per merchant;
* the **customer app** is never linked to an account, even when signed in:
  "what was seen" is a question about content, not about a person.

Bounded like `client_events`: allow-listed event names, at most 8 short
props per event, digit runs scrubbed from text, 50 events per call, IP rate
limit. Rows are purged after `USAGE_EVENTS_RETENTION_DAYS` (app/services/purge.py).
"""

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.security import decode_access_token, require_role
from ..db import get_db
from ..metrics import APP_INSTALLS, USAGE_EVENTS
from ..rate_limiter import limiter

router = APIRouter()

AppName = Literal["user", "retailer"]
Platform = Literal["android", "ios", "web", "other"]

# What each app may report. Anything else is refused, so a typo in an app
# cannot invent a Prometheus label or a column of junk.
EVENT_NAMES: dict[str, frozenset[str]] = {
    "retailer": frozenset({
        "app_open", "screen_view", "sale_form_opened", "sale_recorded", "sale_abandoned",
        "daily_report", "data_used",
    }),
    "user": frozenset({
        "app_open", "screen_view", "tab_view", "venue_viewed", "deal_opened", "media_viewed",
        "scan_opened", "payment_started", "payment_completed", "data_used",
    }),
}

_PROP_KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_DIGITS = re.compile(r"\+?\d[\d ]{3,}\d")

PropValue = str | int | float | bool


class UsageEventIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    props: dict[str, PropValue] | None = None
    count: int = Field(default=1, ge=1, le=10000)
    occurred_at: datetime

    @field_validator("props")
    @classmethod
    def _bounded_props(cls, props: dict[str, PropValue] | None) -> dict[str, PropValue] | None:
        if not props:
            return None
        if len(props) > 8:
            raise ValueError("at most 8 props")
        clean: dict[str, PropValue] = {}
        for key, value in props.items():
            if not _PROP_KEY.match(key):
                raise ValueError(f"invalid prop key: {key!r}")
            if isinstance(value, str):
                # A phone number or an amount typed into a field must never
                # end up here; ids are sent as numbers, not strings.
                value = _DIGITS.sub("<num>", value)[:64]
            clean[key] = value
        return clean


class UsageBatchIn(BaseModel):
    app: AppName
    # Bounded format, because it can become a Prometheus label one day.
    app_version: str = Field(pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,4}(\+\d{1,6})?$")
    platform: Platform
    os_version: str | None = Field(default=None, max_length=64)
    install_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,40}$")
    events: list[UsageEventIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _known_names(self) -> "UsageBatchIn":
        allowed = EVENT_NAMES[self.app]
        unknown = sorted({e.name for e in self.events} - allowed)
        if unknown:
            raise ValueError(f"unknown event names for {self.app}: {', '.join(unknown)}")
        return self


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


async def _merchant_venue_id(request: Request, db: AsyncSession) -> int | None:
    """The signed-in merchant's shop, or None. Never an error: usage from a
    signed-out or expired session is still worth counting, just not per shop."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    payload = decode_access_token(header[7:].strip())
    if not payload or payload.get("role", "merchant") != "merchant" or not isinstance(payload.get("sub"), str):
        return None
    return (
        await db.execute(select(models.Venue.id).where(models.Venue.owner_username == payload["sub"]))
    ).scalars().first()


@router.post("/usage-events", status_code=202)
@limiter.limit("30/minute")
async def report(request: Request, payload: UsageBatchIn, db: AsyncSession = Depends(get_db)):
    now = utcnow()
    # Customers are never tied to an account, even with a token in hand.
    venue_id = await _merchant_venue_id(request, db) if payload.app == "retailer" else None
    for event in payload.events:
        occurred = _naive_utc(event.occurred_at)
        # Old phones often have clocks years off; trust ours then.
        if abs(occurred - now) > timedelta(days=30):
            occurred = now
        db.add(
            models.UsageEvent(
                app=payload.app, install_id=payload.install_id, venue_id=venue_id, name=event.name,
                props=json.dumps(event.props, separators=(",", ":")) if event.props else None,
                count=event.count, app_version=payload.app_version, platform=payload.platform,
                os_version=_DIGITS.sub("<num>", payload.os_version) if payload.os_version else None,
                occurred_at=occurred, received_at=now,
            )
        )
        USAGE_EVENTS.labels(app=payload.app, name=event.name).inc(event.count)
        if event.name == "app_open" and (event.props or {}).get("first") is True:
            APP_INSTALLS.labels(app=payload.app).inc()
    await db.commit()
    return {"accepted": len(payload.events)}


# ── Admin summary ────────────────────────────────────────────────────────────


class CountOut(BaseModel):
    key: str
    count: int
    installs: int


class ContentOut(BaseModel):
    id: int
    name: str | None
    views: int
    installs: int


class MerchantOut(BaseModel):
    venue_id: int
    venue_name: str | None
    last_seen: datetime
    app_version: str
    active_days: int
    sale_forms_opened: int
    sales_recorded_in_app: int
    sales_abandoned: int
    median_sale_seconds: float | None
    daily_reports: int
    # Sales the server holds for those report days ÷ the merchant's own
    # estimate: the pilot's master metric (share of real sales recorded).
    recorded_share: float | None
    data_kb_per_active_day: float | None


class UsageSummaryOut(BaseModel):
    app: str
    days: int
    installs_total: int
    installs_in_period: int
    active_installs_1d: int
    active_installs_7d: int
    active_installs_30d: int
    events: list[CountOut]
    screens: list[CountOut]
    venues_viewed: list[ContentOut]
    deals_opened: list[ContentOut]
    merchants: list[MerchantOut]
    data_kb_per_active_install_day: float | None


def _props(row: models.UsageEvent) -> dict:
    try:
        return json.loads(row.props) if row.props else {}
    except ValueError:
        return {}


def _top(counter: Counter, installs: dict, limit: int = 20) -> list[CountOut]:
    return [CountOut(key=k, count=c, installs=len(installs[k])) for k, c in counter.most_common(limit)]


@router.get("/admin/usage", response_model=UsageSummaryOut)
async def summary(
    app: AppName,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("admin")),
):
    """Installs, active installs, screens and content seen; per merchant for
    the merchant app.

    Aggregated in Python over the period's rows: pilot volumes are thousands
    of rows, and it keeps the JSON props portable between SQLite (tests) and
    Postgres. Move to SQL views before the volume says so."""
    E = models.UsageEvent
    now = utcnow()
    since = now - timedelta(days=days)

    first_opens = select(E.install_id).where(E.app == app, E.name == "app_open", E.props.like('%"first":true%'))
    installs_total = (await db.execute(select(func.count(func.distinct(E.install_id))).where(E.app == app))).scalar_one()
    installs_in_period = (
        await db.execute(select(func.count(func.distinct(E.install_id))).where(E.install_id.in_(first_opens.where(E.occurred_at >= since))))
    ).scalar_one()

    async def active(window: timedelta) -> int:
        return (
            await db.execute(select(func.count(func.distinct(E.install_id))).where(E.app == app, E.occurred_at >= now - window))
        ).scalar_one()

    rows = (await db.execute(select(E).where(E.app == app, E.occurred_at >= since))).scalars().all()

    events, screens = Counter(), Counter()
    event_installs, screen_installs = defaultdict(set), defaultdict(set)
    venue_views, deal_views = Counter(), Counter()
    venue_installs, deal_installs = defaultdict(set), defaultdict(set)
    data_bytes: dict[tuple[str, date], int] = defaultdict(int)
    for row in rows:
        props = _props(row)
        events[row.name] += row.count
        event_installs[row.name].add(row.install_id)
        if row.name in ("screen_view", "tab_view") and isinstance(props.get("screen"), str):
            screens[props["screen"]] += row.count
            screen_installs[props["screen"]].add(row.install_id)
        elif row.name == "venue_viewed" and isinstance(props.get("venue_id"), int):
            venue_views[props["venue_id"]] += row.count
            venue_installs[props["venue_id"]].add(row.install_id)
        elif row.name == "deal_opened" and isinstance(props.get("deal_id"), int):
            deal_views[props["deal_id"]] += row.count
            deal_installs[props["deal_id"]].add(row.install_id)
        elif row.name == "data_used":
            sent, received = props.get("bytes_sent", 0), props.get("bytes_received", 0)
            if isinstance(sent, int) and isinstance(received, int):
                data_bytes[(row.install_id, row.occurred_at.date())] += sent + received

    async def labels(column, ids) -> dict[int, str]:
        if not ids:
            return {}
        model = column.class_
        return dict((await db.execute(select(model.id, column).where(model.id.in_(list(ids))))).all())

    venue_names = await labels(models.Venue.name, venue_views)
    deal_names = await labels(models.Deal.title, deal_views)

    def content(counter: Counter, installs: dict, labels: dict) -> list[ContentOut]:
        return [ContentOut(id=k, name=labels.get(k), views=c, installs=len(installs[k])) for k, c in counter.most_common(20)]

    merchants = await _merchants(db, rows, since) if app == "retailer" else []

    return UsageSummaryOut(
        app=app, days=days, installs_total=installs_total, installs_in_period=installs_in_period,
        active_installs_1d=await active(timedelta(days=1)),
        active_installs_7d=await active(timedelta(days=7)),
        active_installs_30d=await active(timedelta(days=30)),
        events=_top(events, event_installs), screens=_top(screens, screen_installs),
        venues_viewed=content(venue_views, venue_installs, venue_names),
        deals_opened=content(deal_views, deal_installs, deal_names),
        merchants=merchants,
        data_kb_per_active_install_day=round(sum(data_bytes.values()) / len(data_bytes) / 1024, 1) if data_bytes else None,
    )


async def _merchants(db: AsyncSession, rows, since: datetime) -> list[MerchantOut]:
    by_venue: dict[int, list] = defaultdict(list)
    for row in rows:
        if row.venue_id is not None:
            by_venue[row.venue_id].append(row)
    if not by_venue:
        return []
    venue_names = dict(
        (await db.execute(select(models.Venue.id, models.Venue.name).where(models.Venue.id.in_(list(by_venue))))).all()
    )
    S = models.SaleEvent
    sales_per_day: dict[tuple[int, date], int] = defaultdict(int)
    for venue_id, occurred in (
        await db.execute(select(S.venue_id, S.occurred_at).where(S.venue_id.in_(list(by_venue)), S.occurred_at >= since))
    ).all():
        sales_per_day[(venue_id, occurred.date())] += 1

    out = []
    for venue_id, venue_rows in by_venue.items():
        count = Counter()
        durations: list[float] = []
        estimates: dict[date, int] = {}
        data_bytes: dict[date, int] = defaultdict(int)
        for row in venue_rows:
            props = _props(row)
            count[row.name] += row.count
            if row.name == "sale_recorded" and isinstance(props.get("seconds"), (int, float)):
                durations.append(float(props["seconds"]))
            elif row.name == "daily_report" and isinstance(props.get("sales_estimate"), int):
                estimates[row.occurred_at.date()] = props["sales_estimate"]
            elif row.name == "data_used":
                sent, received = props.get("bytes_sent", 0), props.get("bytes_received", 0)
                if isinstance(sent, int) and isinstance(received, int):
                    data_bytes[row.occurred_at.date()] += sent + received
        estimated = sum(estimates.values())
        recorded = sum(sales_per_day[(venue_id, day)] for day in estimates)
        latest = max(venue_rows, key=lambda r: r.occurred_at)
        out.append(
            MerchantOut(
                venue_id=venue_id, venue_name=venue_names.get(venue_id), last_seen=latest.occurred_at,
                app_version=latest.app_version, active_days=len({r.occurred_at.date() for r in venue_rows}),
                sale_forms_opened=count["sale_form_opened"], sales_recorded_in_app=count["sale_recorded"],
                sales_abandoned=count["sale_abandoned"],
                median_sale_seconds=round(statistics.median(durations), 1) if durations else None,
                daily_reports=len(estimates),
                recorded_share=round(min(recorded / estimated, 1.0), 2) if estimated else None,
                data_kb_per_active_day=round(sum(data_bytes.values()) / len(data_bytes) / 1024, 1) if data_bytes else None,
            )
        )
    return sorted(out, key=lambda m: m.last_seen, reverse=True)
