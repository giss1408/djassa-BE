from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app
from app.seed import seed_sample_data


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _auth(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _in(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.mark.asyncio
async def test_categories_and_other_retailers(client):
    h = await _auth(client, "client", "client123")
    cats = (await client.get("/api/categories", headers=h)).json()
    keys = [c["key"] for c in cats]
    assert keys[0] == "maquis" and {"pharmacy", "superette", "mode"} <= set(keys)

    shops = (await client.get("/api/venues", params={"category": "superette"}, headers=h)).json()
    assert shops and all(v["category"] == "superette" for v in shops)

    # No category: every kind of venue.
    everything = (await client.get("/api/venues", headers=h)).json()
    assert {"maquis", "pharmacy", "superette"} <= {v["category"] for v in everything}


@pytest.mark.asyncio
async def test_deal_feed_is_sponsored_first_then_ending_soonest(client):
    h = await _auth(client, "client", "client123")
    deals = (await client.get("/api/deals", headers=h)).json()
    assert deals and all(d["is_sample"] for d in deals)
    featured = [d["is_featured"] for d in deals]
    assert featured == sorted(featured, reverse=True), "sponsored deals come first"
    organic = [d["ends_at"] for d in deals if not d["is_featured"]]
    assert organic == sorted(organic)

    only_featured = (await client.get("/api/deals", params={"featured": "true"}, headers=h)).json()
    assert only_featured and all(d["is_featured"] for d in only_featured)

    mode = (await client.get("/api/deals", params={"category": "mode"}, headers=h)).json()
    assert mode and all(d["venue_category"] == "mode" for d in mode)

    # A venue page lists its own live deals.
    venue_id = deals[0]["venue_id"]
    detail = (await client.get(f"/api/venues/{venue_id}", headers=h)).json()
    assert any(d["id"] == deals[0]["id"] for d in detail["deals"])


@pytest.mark.asyncio
async def test_merchant_publishes_and_ends_a_deal_but_cannot_feature_it(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")

    r = await client.post(
        "/api/merchant/deals",
        json={"title": "Brochettes a 500 F", "price": 500, "original_price": 800, "ends_at": _in(2), "is_featured": True},
        headers=merchant,
    )
    assert r.status_code == 201, r.text
    deal = r.json()
    assert deal["is_featured"] is False, "the featured slot is sold by an admin, never self-granted"

    feed = (await client.get("/api/deals", headers=customer)).json()
    assert any(d["id"] == deal["id"] for d in feed)

    # Only an admin can sell the slot.
    slot = {"ends_at": _in(1), "price": 5000}
    assert (await client.post(f"/api/admin/deals/{deal['id']}/placements", json=slot, headers=merchant)).status_code == 403
    admin = await _auth(client, "admin", "admin123")
    r = await client.post(f"/api/admin/deals/{deal['id']}/placements", json=slot, headers=admin)
    assert r.status_code == 201, r.text
    assert r.json()["is_live"] is True
    promoted = (await client.get("/api/deals", params={"featured": "true"}, headers=customer)).json()
    assert any(d["id"] == deal["id"] for d in promoted)

    assert (await client.delete(f"/api/merchant/deals/{deal['id']}", headers=merchant)).status_code == 204
    feed = (await client.get("/api/deals", headers=customer)).json()
    assert all(d["id"] != deal["id"] for d in feed)


@pytest.mark.asyncio
async def test_deal_validation(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")

    # Already over.
    r = await client.post("/api/merchant/deals", json={"title": "Trop tard", "discount_percent": 10, "ends_at": _in(-1)}, headers=merchant)
    assert r.status_code == 422
    # Nothing on offer.
    r = await client.post("/api/merchant/deals", json={"title": "Rien", "ends_at": _in(1)}, headers=merchant)
    assert r.status_code == 422
    # A "promo" dearer than the original.
    r = await client.post(
        "/api/merchant/deals", json={"title": "Faux", "price": 900, "original_price": 800, "ends_at": _in(1)}, headers=merchant
    )
    assert r.status_code == 422
    # Customers cannot publish.
    r = await client.post("/api/merchant/deals", json={"title": "Moi", "discount_percent": 10, "ends_at": _in(1)}, headers=customer)
    assert r.status_code == 403
    # Unknown category.
    assert (await client.get("/api/deals", params={"category": "bar"}, headers=customer)).status_code == 422
