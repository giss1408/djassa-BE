"""Enrolling a merchant: by an agent in one call, or by the merchant's own
request from Fidelia Pro, reviewed by an admin."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.helpers import TEST_PASSWORD, demo_login
from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from tests.helpers import make_user, send_open_check, sign_in

PHONE = "07 44 55 66 77"
E164 = "+2250744556677"


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


async def _admin(ac):
    r = await demo_login(ac, data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _merchant_sign_in(ac, phone=PHONE):
    """A merchant made by the team has no password: the team sends a temporary
    one, and the first thing they do is choose their own."""
    r = await sign_in(ac, phone, "merchant", password=await send_open_check(phone, "reset_password"))
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return await ac.post("/api/auth/password", json={"new": TEST_PASSWORD}, headers=h)


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
    assert venue["qr_payload"].startswith("fidelia://pay/")

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
    r = await demo_login(client, data={"username": "demo", "password": "demo123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/api/admin/venues", json=SHOP, headers=h)).status_code == 403


async def _file_request(ac, **extra):
    body = {"phone": PHONE, "contact_name": "Awa Kone", "shop_name": "Chez Awa",
            "category": "maquis", "commune": "Abobo", "wallet_provider": "wave", **extra}
    return await ac.post("/api/partner-requests", json=body)


@pytest.mark.asyncio
async def test_merchant_asks_to_join_and_an_admin_approves(client):
    await make_user(PHONE)
    r = await _file_request(client)
    assert r.status_code == 202, r.text
    # Not a merchant until approved.
    assert (await sign_in(client, PHONE, "merchant")).status_code == 403

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

    # Already registered with a password: they keep it.
    signed = await sign_in(client, PHONE, "merchant")
    assert signed.status_code == 200
    assert (await client.post(f"/api/admin/partner-requests/{request['id']}/approve", json={}, headers=admin)).status_code == 409


@pytest.mark.asyncio
async def test_partner_request_without_code(client):
    assert (await client.post("/api/partner-requests/code", json={"phone": PHONE})).status_code == 404
    body = {"phone": PHONE, "contact_name": "Awa", "shop_name": "Chez Awa", "category": "maquis", "commune": "Abobo"}
    assert (await client.post("/api/partner-requests", json=body)).status_code == 202
    # One at a time.
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
