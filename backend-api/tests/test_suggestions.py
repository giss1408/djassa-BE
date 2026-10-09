"""The WhatsApp suggestion line: free for shops, unlocked at 100 points for customers."""

from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data

URL = "/api/support/suggestions/whatsapp"


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setenv("FIDELIA_SUGGESTIONS_WHATSAPP", "+225 07 00 00 00 01")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _auth(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _points(customer_id, points):
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
        db.add(models.LoyaltyEntry(customer_id=customer_id, venue_id=venue.id, points=points, reason="payment",
                                   created_at=datetime.now()))
        await db.commit()


@pytest.mark.asyncio
async def test_merchants_always_have_it_free(client):
    r = (await client.get(URL, headers=await _auth(client, "demo", "demo123"))).json()
    assert r["available"] is True
    assert r["whatsapp_url"].startswith("https://wa.me/2250700000001?text=")
    assert "commercant" in r["whatsapp_url"]


@pytest.mark.asyncio
async def test_customers_unlock_it_at_100_points_without_spending_them(client):
    h = await _auth(client, "client", "client123")
    await _points("client", 99)
    r = (await client.get(URL, headers=h)).json()
    assert r["available"] is False and r["whatsapp_url"] is None and r["points"] == 99

    await _points("client", 1)
    r = (await client.get(URL, headers=h)).json()
    assert r["available"] is True and "client" in r["whatsapp_url"]
    # Asking twice spends nothing.
    assert (await client.get(URL, headers=h)).json()["points"] == 100


@pytest.mark.asyncio
async def test_hidden_until_the_number_is_configured(client, monkeypatch):
    monkeypatch.delenv("FIDELIA_SUGGESTIONS_WHATSAPP")
    r = (await client.get(URL, headers=await _auth(client, "demo", "demo123"))).json()
    assert r["available"] is False
