"""The pilot record and scorecard: a baseline that provably came first, a
commitment that names its price, and every rate shown with its counts."""

import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.helpers import demo_login
from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data


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
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _admin(ac):
    r = await demo_login(ac, data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _shop(name="Maquis Chez Tanti"):
    async with AsyncSessionLocal() as db:
        venue = models.Venue(category="maquis", name=name, commune="Yopougon", is_sample=False, points_per_100=1)
        db.add(venue)
        await db.commit()
        return venue.id


async def _sale(venue_id, when, customer=None, key=None):
    async with AsyncSessionLocal() as db:
        db.add(models.SaleEvent(
            venue_id=venue_id, source="cash_declared", amount=2000, occurred_at=when, recorded_at=when,
            customer_id=customer, idempotency_key=key or f"sale:{venue_id}:{when.isoformat()}:{customer}",
            created_at=when,
        ))
        await db.commit()


async def _daily_report(venue_id, when, estimate):
    async with AsyncSessionLocal() as db:
        db.add(models.UsageEvent(
            app="retailer", install_id="inst_0123456789abcdef", venue_id=venue_id, name="daily_report",
            props=json.dumps({"sales_estimate": estimate}), app_version="0.3.0", platform="android",
            occurred_at=when, received_at=when,
        ))
        await db.commit()


async def _offer_use(venue_id, when, new, key):
    async with AsyncSessionLocal() as db:
        deal = models.Deal(venue_id=venue_id, title="Poulet braise -20%", starts_at=when, ends_at=when + timedelta(days=7), created_at=when)
        db.add(deal)
        await db.flush()
        db.add(models.DealUse(deal_id=deal.id, venue_id=venue_id, new_customer=new, idempotency_key=key, recorded_by="tel:+2250700000002", created_at=when))
        await db.commit()


@pytest.mark.asyncio
async def test_a_venue_joins_the_pilot_with_its_baseline_dated_by_the_server(client):
    h = await _admin(client)
    venue = await _shop()
    r = await client.get(f"/api/admin/venues/{venue}/pilot", headers=h)
    assert r.status_code == 200 and r.json()["in_pilot"] is False

    r = await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={
        "baseline_tickets_per_day": 40, "baseline_average_basket": 4000, "baseline_mobile_money_pct": 60,
        "baseline_repeat_pct": 30, "owner_gender": "woman",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["in_pilot"] is True and body["baseline_repeat_pct"] == 30 and body["owner_gender"] == "woman"
    assert body["baseline_recorded_at"] is not None
    # No sale yet: the baseline came first.
    assert body["baseline_before_first_sale"] is True

    # A later correction keeps the original baseline date.
    first_date = body["baseline_recorded_at"]
    r = await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={"baseline_repeat_pct": 35})
    assert r.json()["baseline_recorded_at"] == first_date and r.json()["baseline_tickets_per_day"] == 40


@pytest.mark.asyncio
async def test_a_baseline_taken_after_the_first_sale_is_flagged(client):
    h = await _admin(client)
    venue = await _shop()
    await _sale(venue, _now() - timedelta(days=3))
    r = await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={"baseline_repeat_pct": 30})
    assert r.json()["baseline_before_first_sale"] is False


@pytest.mark.asyncio
async def test_a_commitment_names_its_plan_and_price(client):
    h = await _admin(client)
    venue = await _shop()
    r = await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={"commitment": "committed"})
    assert r.status_code == 422
    async with AsyncSessionLocal() as db:
        # The refused call left nothing behind.
        assert (await db.execute(select(models.PilotMerchant))).scalars().all() == []

    r = await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={
        "commitment": "committed", "commitment_plan": "starter", "commitment_price": 5000,
    })
    assert r.status_code == 200 and r.json()["commitment_at"] is not None

    r = await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={"commitment": None})
    assert r.json()["commitment"] is None and r.json()["commitment_at"] is None


@pytest.mark.asyncio
async def test_only_admins_and_never_sample_shops(client):
    venue = await _shop()
    assert (await client.get(f"/api/admin/venues/{venue}/pilot")).status_code == 401
    h = await _admin(client)
    async with AsyncSessionLocal() as db:
        sample = (await db.execute(select(models.Venue.id).where(models.Venue.is_sample.is_(True)))).scalars().first()
    assert (await client.put(f"/api/admin/venues/{sample}/pilot", headers=h, json={"owner_gender": "man"})).status_code == 422
    assert (await client.put("/api/admin/venues/999999/pilot", headers=h, json={})).status_code == 404
    assert (await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={"owner_gender": "other"})).status_code == 422


@pytest.mark.asyncio
async def test_scorecard_reports_each_merchant_with_counts(client):
    h = await _admin(client)
    tanti, awa, outside = await _shop("Maquis Chez Tanti"), await _shop("Superette Awa"), await _shop("Pas dans le pilote")
    await client.put(f"/api/admin/venues/{tanti}/pilot", headers=h, json={"baseline_repeat_pct": 30, "owner_gender": "woman"})
    await client.put(f"/api/admin/venues/{awa}/pilot", headers=h, json={
        "owner_gender": "undisclosed", "commitment": "committed", "commitment_plan": "starter", "commitment_price": 5000,
    })

    day = _now().replace(hour=12, minute=0, second=0, microsecond=0)
    # Tanti, yesterday: 8 sales held against an estimate of 10 -> 0.8.
    yesterday = day - timedelta(days=1)
    for i in range(8):
        await _sale(tanti, yesterday + timedelta(minutes=i), key=f"t{i}")
    await _daily_report(tanti, yesterday + timedelta(hours=8), 10)
    # Identified customers: A on two days (returns), B once.
    await _sale(tanti, day - timedelta(days=5), customer="tel:+2250701010101", key="a1")
    await _sale(tanti, day - timedelta(days=2), customer="tel:+2250701010101", key="a2")
    await _sale(tanti, day - timedelta(days=2), customer="tel:+2250702020202", key="b1")
    # Two offers used at the counter, one by a new customer; one too old to count.
    await _offer_use(tanti, day - timedelta(days=1), True, "u1")
    await _offer_use(tanti, day - timedelta(days=1), False, "u2")
    await _offer_use(tanti, day - timedelta(days=60), True, "u3")
    await _sale(outside, day, key="o1")

    r = await client.get("/api/admin/pilot/scorecard", headers=h)
    assert r.status_code == 200, r.text
    card = r.json()
    assert [row["venue_name"] for row in card["rows"]] == ["Maquis Chez Tanti", "Superette Awa"]
    assert (card["merchants"], card["women"], card["with_baseline"], card["committed"]) == (2, 1, 1, 1)
    assert (card["recording_70"], card["recording_85"], card["with_new_customers"]) == (1, 0, 1)

    tanti_row = card["rows"][0]
    assert tanti_row["recorded_share"] == 0.8 and tanti_row["daily_reports"] == 1
    assert (tanti_row["identified_customers"], tanti_row["returning_customers"], tanti_row["repeat_pct"]) == (2, 1, 50)
    assert (tanti_row["baseline_repeat_pct"], tanti_row["repeat_lift_pts"]) == (30, 20)
    # The baseline was recorded today, after sales dated days ago: flagged.
    assert tanti_row["baseline_before_first_sale"] is False
    assert (tanti_row["offer_uses"], tanti_row["new_customers_from_offers"]) == (2, 1)

    awa_row = card["rows"][1]
    assert awa_row["recorded_share"] is None and awa_row["repeat_pct"] is None and awa_row["repeat_lift_pts"] is None
    assert (awa_row["commitment"], awa_row["commitment_plan"], awa_row["commitment_price"]) == ("committed", "starter", 5000)


@pytest.mark.asyncio
async def test_scorecard_is_admin_only(client):
    assert (await client.get("/api/admin/pilot/scorecard")).status_code == 401


@pytest.mark.asyncio
async def test_a_new_owner_does_not_inherit_the_previous_owners_gender(client):
    h = await _admin(client)
    venue = await _shop()
    assert (await client.patch(f"/api/admin/venues/{venue}", headers=h, json={"merchant_phone": "07 11 22 33 44"})).status_code == 200
    await client.put(f"/api/admin/venues/{venue}/pilot", headers=h, json={"owner_gender": "woman", "baseline_repeat_pct": 30})
    # Same owner again: nothing changes.
    await client.patch(f"/api/admin/venues/{venue}", headers=h, json={"merchant_phone": "07 11 22 33 44"})
    assert (await client.get(f"/api/admin/venues/{venue}/pilot", headers=h)).json()["owner_gender"] == "woman"
    # A new owner: the gender goes, the shop's baseline stays.
    assert (await client.patch(f"/api/admin/venues/{venue}", headers=h, json={"merchant_phone": "07 55 66 77 88"})).status_code == 200
    body = (await client.get(f"/api/admin/venues/{venue}/pilot", headers=h)).json()
    assert body["owner_gender"] is None and body["baseline_repeat_pct"] == 30
