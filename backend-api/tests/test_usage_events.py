"""App usage: installs counted per install id, merchants measured per shop,
customers never tied to an account, everything bounded and scrubbed."""

import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from app.services.purge import purge_expired

INSTALL = "inst_0123456789abcdef"


@pytest_asyncio.fixture
async def client():
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


def _now():
    return datetime.now(timezone.utc).isoformat()


def _batch(app_name="user", install_id=INSTALL, events=None):
    return {
        "app": app_name, "app_version": "0.3.0+7", "platform": "android", "os_version": "Android 5.1",
        "install_id": install_id,
        "events": events or [{"name": "app_open", "props": {"first": True}, "occurred_at": _now()}],
    }


async def _auth(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _rows():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.UsageEvent).order_by(models.UsageEvent.id))).scalars().all()


@pytest.mark.asyncio
async def test_accepted_without_sign_in(client):
    r = await client.post("/api/usage-events", json=_batch())
    assert r.status_code == 202
    [row] = await _rows()
    assert (row.app, row.install_id, row.name, row.venue_id) == ("user", INSTALL, "app_open", None)
    assert json.loads(row.props) == {"first": True}


@pytest.mark.asyncio
async def test_unknown_event_names_and_oversized_batches_are_refused(client):
    assert (await client.post("/api/usage-events", json=_batch(events=[
        {"name": "sale_recorded", "occurred_at": _now()},  # a merchant event, from the customer app
    ]))).status_code == 422
    assert (await client.post("/api/usage-events", json=_batch(events=[
        {"name": "app_open", "occurred_at": _now()}] * 51))).status_code == 422
    assert (await client.post("/api/usage-events", json=_batch(install_id="short"))).status_code == 422
    assert (await client.post("/api/usage-events", json=_batch(events=[
        {"name": "screen_view", "props": {f"k{i}": i for i in range(9)}, "occurred_at": _now()},
    ]))).status_code == 422
    assert await _rows() == []


@pytest.mark.asyncio
async def test_digit_runs_are_scrubbed_from_text_props(client):
    await client.post("/api/usage-events", json=_batch(events=[
        {"name": "screen_view", "props": {"screen": "pay +225 07 00 00 00 88"}, "occurred_at": _now()},
    ]))
    [row] = await _rows()
    assert "0700" not in row.props and "<num>" in json.loads(row.props)["screen"]


@pytest.mark.asyncio
async def test_merchant_usage_is_tied_to_the_shop_customer_usage_never_is(client):
    merchant = await _auth(client, "demo", "demo123")
    await client.post("/api/usage-events", headers=merchant, json=_batch(
        "retailer", events=[{"name": "sale_form_opened", "occurred_at": _now()}]))
    # The same token sent by the customer app is ignored.
    await client.post("/api/usage-events", headers=merchant, json=_batch(
        "user", install_id="inst_customer_000001", events=[{"name": "tab_view", "props": {"screen": "home"}, "occurred_at": _now()}]))
    # An invalid token still counts the event, just not per shop.
    await client.post("/api/usage-events", headers={"Authorization": "Bearer nope"}, json=_batch(
        "retailer", install_id="inst_retailer_00002", events=[{"name": "app_open", "occurred_at": _now()}]))
    merchant_row, customer_row, anonymous_row = await _rows()
    async with AsyncSessionLocal() as db:
        demo_venue = (await db.execute(select(models.Venue.id).where(models.Venue.owner_username == "demo"))).scalar_one()
    assert merchant_row.venue_id == demo_venue
    assert customer_row.venue_id is None and anonymous_row.venue_id is None


@pytest.mark.asyncio
async def test_summary_counts_installs_active_users_and_content_seen(client):
    admin = await _auth(client, "admin", "admin123")
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
    for n in range(3):
        await client.post("/api/usage-events", json=_batch(install_id=f"inst_customer_{n:06d}", events=[
            {"name": "app_open", "props": {"first": True}, "occurred_at": _now()},
            {"name": "tab_view", "props": {"screen": "home"}, "count": 2, "occurred_at": _now()},
            {"name": "venue_viewed", "props": {"venue_id": venue.id}, "occurred_at": _now()},
            {"name": "data_used", "props": {"bytes_sent": 1024, "bytes_received": 9216}, "occurred_at": _now()},
        ]))
    # A returning install: not a new install.
    await client.post("/api/usage-events", json=_batch(install_id="inst_customer_000000", events=[
        {"name": "app_open", "occurred_at": _now()}]))

    r = await client.get("/api/admin/usage", params={"app": "user", "days": 30}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["installs_total"] == 3 and body["installs_in_period"] == 3
    assert body["active_installs_7d"] == 3
    assert {"key": "home", "count": 6, "installs": 3} in body["screens"]
    assert body["venues_viewed"] == [{"id": venue.id, "name": venue.name, "views": 3, "installs": 3}]
    assert body["data_kb_per_active_install_day"] == 10.0

    # Admin only.
    merchant = await _auth(client, "demo", "demo123")
    assert (await client.get("/api/admin/usage", params={"app": "user"}, headers=merchant)).status_code == 403


@pytest.mark.asyncio
async def test_merchant_summary_computes_the_recorded_share(client):
    """Sales the server holds ÷ the merchant's own end-of-day estimate."""
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    for key in ("pilot-share-0001", "pilot-share-0002"):
        r = await client.post("/api/merchant/sales", headers=merchant, json={
            "amount": 1500, "type": "cash", "idempotency_key": key, "occurred_at": _now()})
        assert r.status_code == 201, r.text
    await client.post("/api/usage-events", headers=merchant, json=_batch("retailer", events=[
        {"name": "sale_form_opened", "count": 3, "occurred_at": _now()},
        {"name": "sale_recorded", "props": {"seconds": 12}, "occurred_at": _now()},
        {"name": "sale_recorded", "props": {"seconds": 20}, "occurred_at": _now()},
        {"name": "sale_abandoned", "props": {"step": "amount"}, "occurred_at": _now()},
        {"name": "daily_report", "props": {"sales_estimate": 8}, "occurred_at": _now()},
    ]))
    body = (await client.get("/api/admin/usage", params={"app": "retailer"}, headers=admin)).json()
    [row] = body["merchants"]
    assert row["sale_forms_opened"] == 3 and row["sales_recorded_in_app"] == 2 and row["sales_abandoned"] == 1
    assert row["median_sale_seconds"] == 16.0
    assert row["daily_reports"] == 1
    # The seed may hold sales of its own for today: count what the server has.
    async with AsyncSessionLocal() as db:
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        held = sum(1 for (occurred,) in (await db.execute(
            select(models.SaleEvent.occurred_at).where(models.SaleEvent.venue_id == row["venue_id"])
        )).all() if occurred.date() == today)
    assert held >= 2
    assert row["recorded_share"] == round(min(held / 8, 1.0), 2)


@pytest.mark.asyncio
async def test_old_rows_are_purged(client):
    await client.post("/api/usage-events", json=_batch())
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(models.UsageEvent))).scalar_one()
        row.received_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=401)
        await db.commit()
    assert (await purge_expired())["usage_events"] == 1
    assert await _rows() == []
