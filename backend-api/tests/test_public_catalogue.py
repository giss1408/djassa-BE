"""The customer app shows offers, shops and pharmacies before any sign-in.

Browsing is anonymous; paying, points and the rest of the customer's own data
still need an account."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _auth(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_anyone_can_browse_offers_shops_and_pharmacies(client):
    assert (await client.get("/api/categories")).status_code == 200
    deals = await client.get("/api/deals")
    assert deals.status_code == 200 and deals.json()
    assert "ribbon" in deals.json()[0]
    venues = (await client.get("/api/venues")).json()
    assert venues
    detail = await client.get(f"/api/venues/{venues[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["my_points"] == 0
    assert (await client.get("/api/pharmacies/on-duty")).status_code == 200


@pytest.mark.asyncio
async def test_paying_points_and_history_still_need_an_account(client):
    for path in ("/api/customer/loyalty", "/api/customer/payments", "/api/customer/loyalty-consent",
                 "/api/support/suggestions/whatsapp"):
        assert (await client.get(path)).status_code == 401, path
    r = await client.post("/api/customer/payments", json={"pay_code": "X", "amount": 100, "wallet_provider": "wave",
                                                          "payer_msisdn": "0700000000", "idempotency_key": "k" * 16})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_stale_token_is_refused_not_quietly_treated_as_anonymous(client):
    venues = (await client.get("/api/venues")).json()
    r = await client.get(f"/api/venues/{venues[0]['id']}", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_the_public_catalogue_is_rate_limited_per_address(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_READ_RATE_LIMIT", "3/minute")
    limiter.reset()
    codes = [(await client.get("/api/deals")).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    limiter.reset()


@pytest.mark.asyncio
async def test_restaurants_are_a_category_of_their_own(client):
    keys = [c["key"] for c in (await client.get("/api/categories")).json()]
    assert keys[:2] == ["maquis", "restaurant"]
    restaurants = (await client.get("/api/venues", params={"category": "restaurant"})).json()
    assert restaurants and all(v["category"] == "restaurant" for v in restaurants)
    maquis = (await client.get("/api/venues", params={"category": "maquis"})).json()
    assert not {v["id"] for v in maquis} & {v["id"] for v in restaurants}
