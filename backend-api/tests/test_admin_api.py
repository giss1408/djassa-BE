"""What the djassa-Admin screen relies on: admin phone sign-in, shops, users."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import DEV_ADMIN_PHONE, seed_sample_data


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setenv("OTP_SENDER", "console")
    monkeypatch.setenv("OTP_DEV_ECHO", "1")
    monkeypatch.delenv("DJASSA_ENV", raising=False)
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


async def _phone_session(ac, phone, app_name):
    code = (await ac.post("/api/auth/otp/request", json={"phone": phone, "app": app_name})).json()["dev_code"]
    return await ac.post("/api/auth/otp/verify", json={"phone": phone, "code": code, "app": app_name})


async def _admin(ac):
    r = await _phone_session(ac, DEV_ADMIN_PHONE, "admin")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_signs_in_by_phone_and_others_cannot(client):
    assert (await _phone_session(client, DEV_ADMIN_PHONE, "admin")).json()["role"] == "admin"
    r = await _phone_session(client, "07 12 34 56 78", "admin")
    assert r.status_code == 403
    assert "administration" in r.json()["detail"]


@pytest.mark.asyncio
async def test_list_search_and_edit_a_shop(client):
    admin = await _admin(client)
    shops = (await client.get("/api/admin/venues", headers=admin)).json()
    assert len(shops) > 5
    assert {"images", "videos", "has_merchant"} <= set(shops[0])

    found = (await client.get("/api/admin/venues", params={"q": "tantie"}, headers=admin)).json()
    assert [s["name"] for s in found] == ["Chez Tantie Awa (exemple)"]
    assert found[0]["has_merchant"] is True

    venue_id = found[0]["id"]
    detail = (await client.get(f"/api/admin/venues/{venue_id}", headers=admin)).json()
    assert detail["merchant_phone"] == "+2250700000002"

    r = await client.patch(f"/api/admin/venues/{venue_id}", json={"opening_hours": "10h - 23h", "points_per_100": 3}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["opening_hours"] == "10h - 23h"
    assert r.json()["points_per_100"] == 3
    assert r.json()["name"] == "Chez Tantie Awa (exemple)"  # untouched


@pytest.mark.asyncio
async def test_adding_a_wallet_issues_the_payment_qr(client):
    admin = await _admin(client)
    venue = (await client.post("/api/admin/venues", json={"category": "mode", "name": "Boutique Ama", "commune": "Adjame"}, headers=admin)).json()
    assert venue["pay_code"] is None
    r = await client.patch(f"/api/admin/venues/{venue['id']}", json={"payout_provider": "orange", "payout_account": "07 01 01 01 01"}, headers=admin)
    assert r.json()["pay_code"]
    assert r.json()["payout_account"] == "+2250701010101"


@pytest.mark.asyncio
async def test_find_suspend_and_restore_a_user(client):
    admin = await _admin(client)
    merchant = (await _phone_session(client, "07 00 00 00 02", "merchant")).json()

    user = (await client.get("/api/admin/users", params={"phone": "07 00 00 00 02"}, headers=admin)).json()
    assert user["roles"] == ["merchant"]
    assert user["venues_owned"] == ["Chez Tantie Awa (exemple)"]
    assert user["active_sessions"] == 1

    r = await client.post("/api/admin/users/disable", json={"phone": "07 00 00 00 02", "disabled": True}, headers=admin)
    assert r.json()["disabled"] is True
    assert r.json()["active_sessions"] == 0
    assert (await client.post("/api/auth/refresh", json={"refresh_token": merchant["refresh_token"]})).status_code == 401

    r = await client.post("/api/admin/users/disable", json={"phone": "07 00 00 00 02", "disabled": False}, headers=admin)
    assert r.json()["disabled"] is False


@pytest.mark.asyncio
async def test_revoking_merchant_access(client):
    admin = await _admin(client)
    r = await client.post("/api/admin/users/roles/revoke", json={"phone": "07 00 00 00 02", "role": "merchant"}, headers=admin)
    assert r.json()["roles"] == ["customer"]
    assert (await _phone_session(client, "07 00 00 00 02", "merchant")).status_code == 403


@pytest.mark.asyncio
async def test_an_admin_cannot_lock_themselves_out(client):
    admin = await _admin(client)
    assert (await client.post("/api/admin/users/disable", json={"phone": DEV_ADMIN_PHONE, "disabled": True}, headers=admin)).status_code == 422
    assert (await client.post("/api/admin/users/roles/revoke", json={"phone": DEV_ADMIN_PHONE, "role": "admin"}, headers=admin)).status_code == 422


@pytest.mark.asyncio
async def test_unknown_number_is_404(client):
    admin = await _admin(client)
    assert (await client.get("/api/admin/users", params={"phone": "07 98 98 98 98"}, headers=admin)).status_code == 404
