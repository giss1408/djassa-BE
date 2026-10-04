"""Enrolling a merchant: by an agent in one call, or by the merchant's own
request from Djassa Pro, reviewed by an admin."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data

PHONE = "07 44 55 66 77"
E164 = "+2250744556677"


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


async def _admin(ac):
    r = await ac.post("/api/token", data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _merchant_sign_in(ac, phone=PHONE):
    code = (await ac.post("/api/auth/otp/request", json={"phone": phone, "app": "merchant"})).json()["dev_code"]
    return await ac.post("/api/auth/otp/verify", json={"phone": phone, "code": code, "app": "merchant"})


async def _age_codes(seconds=61):
    from datetime import timedelta
    async with AsyncSessionLocal() as db:
        for c in (await db.execute(select(models.OtpChallenge))).scalars():
            c.created_at -= timedelta(seconds=seconds)
        await db.commit()


SHOP = {
    "category": "maquis", "name": "Maquis Le Fromager", "commune": "Treichville", "address": "Rue 12",
    "payout_provider": "wave", "payout_account": PHONE, "merchant_phone": PHONE, "points_per_100": 2,
}


@pytest.mark.asyncio
async def test_agent_enrols_a_shop_in_one_call(client):
    r = await client.post("/api/admin/venues", json=SHOP, headers=await _admin(client))
    assert r.status_code == 201, r.text
    venue = r.json()
    assert venue["merchant_phone_masked"] == "07 •• •• 66 77"
    assert venue["qr_payload"].startswith("djassa://pay/")

    # The merchant signs in with that number and runs that shop.
    signed = await _merchant_sign_in(client)
    assert signed.status_code == 200, signed.text
    h = {"Authorization": f"Bearer {signed.json()['access_token']}"}
    assert (await client.get("/api/merchant/pay-code", headers=h)).json()["pay_code"] == venue["pay_code"]

    # And customers find it.
    async with AsyncSessionLocal() as db:
        row = await db.get(models.Venue, venue["id"])
        assert row.is_sample is False and row.payout_account == E164


@pytest.mark.asyncio
async def test_a_shop_without_wallet_has_no_payment_qr(client):
    shop = {k: v for k, v in SHOP.items() if k not in ("payout_provider", "payout_account")}
    venue = (await client.post("/api/admin/venues", json=shop, headers=await _admin(client))).json()
    assert venue["pay_code"] is None


@pytest.mark.asyncio
async def test_one_number_runs_one_shop(client):
    admin = await _admin(client)
    assert (await client.post("/api/admin/venues", json=SHOP, headers=admin)).status_code == 201
    r = await client.post("/api/admin/venues", json={**SHOP, "name": "Second shop"}, headers=admin)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_only_admins_create_shops(client):
    r = await client.post("/api/token", data={"username": "demo", "password": "demo123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/api/admin/venues", json=SHOP, headers=h)).status_code == 403


async def _file_request(ac, **extra):
    code = (await ac.post("/api/partner-requests/code", json={"phone": PHONE})).json()["dev_code"]
    body = {"phone": PHONE, "code": code, "contact_name": "Awa Kone", "shop_name": "Chez Awa",
            "category": "maquis", "commune": "Abobo", "wallet_provider": "wave", **extra}
    return await ac.post("/api/partner-requests", json=body)


@pytest.mark.asyncio
async def test_merchant_asks_to_join_and_an_admin_approves(client):
    r = await _file_request(client)
    assert r.status_code == 202, r.text
    # Not a merchant until approved.
    await _age_codes()
    assert (await _merchant_sign_in(client)).status_code == 403

    admin = await _admin(client)
    pending = (await client.get("/api/admin/partner-requests", headers=admin)).json()
    assert len(pending) == 1
    request = pending[0]
    assert request["phone"] == E164
    assert request["wallet_number"] == E164  # defaults to the phone

    # The checklist comes first; the wallet check because the request has one.
    url = f"/api/admin/partner-requests/{request['id']}/approve"
    r = await client.post(url, json={"checks": ["called", "shop_seen"]}, headers=admin)
    assert r.status_code == 422
    assert "Nom du titulaire" in r.json()["detail"]

    r = await client.post(url, json={"name": "Maquis Chez Awa", "points_per_100": 3,
                                     "checks": ["called", "wallet_name_matches", "shop_seen"]}, headers=admin)
    assert r.status_code == 200, r.text
    venue = r.json()
    approved = (await client.get("/api/admin/partner-requests?status=approved", headers=admin)).json()
    assert approved[0]["review_checks"] == ["called", "wallet_name_matches", "shop_seen"]
    assert venue["name"] == "Maquis Chez Awa"
    assert venue["pay_code"]

    await _age_codes(400)
    signed = await _merchant_sign_in(client)
    assert signed.status_code == 200
    assert (await client.post(f"/api/admin/partner-requests/{request['id']}/approve", json={}, headers=admin)).status_code == 409


@pytest.mark.asyncio
async def test_partner_request_needs_the_code_and_only_one_at_a_time(client):
    body = {"phone": PHONE, "code": "000000", "contact_name": "Awa", "shop_name": "Chez Awa",
            "category": "maquis", "commune": "Abobo"}
    assert (await client.post("/api/partner-requests", json=body)).status_code == 401

    assert (await _file_request(client)).status_code == 202
    await _age_codes()
    assert (await _file_request(client)).status_code == 409


@pytest.mark.asyncio
async def test_existing_merchant_is_told_to_sign_in(client):
    r = await client.post("/api/admin/venues", json=SHOP, headers=await _admin(client))
    assert r.status_code == 201
    r = await _file_request(client)
    assert r.status_code == 409
    assert "connectez-vous" in r.json()["detail"]


@pytest.mark.asyncio
async def test_rejecting_a_request(client):
    await _file_request(client)
    admin = await _admin(client)
    request = (await client.get("/api/admin/partner-requests", headers=admin)).json()[0]
    r = await client.post(f"/api/admin/partner-requests/{request['id']}/reject", json={"note": "Hors zone"}, headers=admin)
    assert r.json()["status"] == "rejected"
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.Venue).where(models.Venue.name == "Chez Awa"))).first() is None
