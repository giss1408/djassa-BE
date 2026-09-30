"""The merchant sets the shop's position from the phone's GPS; customers get it.

The customer app's "Itinéraire" button needs coordinates, and the merchant,
standing in the shop, is the most reliable source of them.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data

# Plateau, Abidjan.
PLATEAU = {"latitude": 5.3197, "longitude": -4.0165, "accuracy_m": 12.4}


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _auth(ac, username="demo", password="demo123"):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _my_venue(username="demo"):
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == username))
        ).scalars().first()


@pytest.mark.asyncio
async def test_the_merchant_saves_the_shop_position_and_customers_receive_it(client):
    merchant = await _auth(client)
    r = await client.put("/api/merchant/venue/location", json=PLATEAU, headers=merchant)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["latitude"] == pytest.approx(5.3197)
    assert body["longitude"] == pytest.approx(-4.0165)
    assert body["accuracy_m"] == 12
    assert body["source"] == "merchant_gps"
    assert body["set_at"]

    venue = await _my_venue()
    customer = await _auth(client, "client", "client123")
    detail = await client.get(f"/api/venues/{venue.id}", headers=customer)
    assert detail.status_code == 200
    assert detail.json()["latitude"] == pytest.approx(5.3197)
    assert detail.json()["longitude"] == pytest.approx(-4.0165)


@pytest.mark.asyncio
async def test_the_merchant_can_read_whether_a_position_is_set(client):
    merchant = await _auth(client)
    before = await client.get("/api/merchant/venue/location", headers=merchant)
    assert before.status_code == 200
    await client.put("/api/merchant/venue/location", json=PLATEAU, headers=merchant)
    after = await client.get("/api/merchant/venue/location", headers=merchant)
    assert after.json()["source"] == "merchant_gps"


@pytest.mark.asyncio
async def test_an_imprecise_fix_is_refused_with_advice(client):
    merchant = await _auth(client)
    r = await client.put(
        "/api/merchant/venue/location", json={**PLATEAU, "accuracy_m": 450}, headers=merchant
    )
    assert r.status_code == 422
    assert "imprécise" in r.json()["detail"]


@pytest.mark.parametrize("where", [{"latitude": 48.8566, "longitude": 2.3522}, {"latitude": 0.0, "longitude": 0.0}])
@pytest.mark.asyncio
async def test_a_position_outside_cote_divoire_is_refused(client, where):
    merchant = await _auth(client)
    r = await client.put("/api/merchant/venue/location", json={**where, "accuracy_m": 10}, headers=merchant)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_only_merchants_can_set_a_position(client):
    customer = await _auth(client, "client", "client123")
    r = await client.put("/api/merchant/venue/location", json=PLATEAU, headers=customer)
    assert r.status_code == 403
