"""Cashiers added by a shop owner, and field agents who enrol shops."""

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data

OWNER = "07 00 00 00 02"  # seeded: runs "Chez Tantie Awa (exemple)"
SEEDED_CASHIER = "07 00 00 00 03"
SEEDED_AGENT = "07 00 00 00 04"
CASHIER = "07 11 22 33 44"
CASHIER_KEY = "tel:+2250711223344"


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


async def _age_codes():
    async with AsyncSessionLocal() as db:
        for c in (await db.execute(select(models.OtpChallenge))).scalars():
            c.created_at -= timedelta(seconds=400)
        await db.commit()


async def _sign_in(ac, phone, app_name):
    await _age_codes()
    code = (await ac.post("/api/auth/otp/request", json={"phone": phone, "app": app_name})).json()["dev_code"]
    return await ac.post("/api/auth/otp/verify", json={"phone": phone, "code": code, "app": app_name})


async def _headers(ac, phone, app_name):
    r = await _sign_in(ac, phone, app_name)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()


async def _admin(ac):
    r = await ac.post("/api/token", data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_owner_adds_a_cashier_who_works_the_till_but_not_the_money(client):
    owner, _ = await _headers(client, OWNER, "merchant")
    r = await client.post("/api/merchant/staff", json={"phone": CASHIER, "name": "Koffi"}, headers=owner)
    assert r.status_code == 201, r.text
    assert r.json()["phone_masked"] == "07 •• •• 33 44"
    assert r.json()["last_login_at"] is None

    cashier, pair = await _headers(client, CASHIER, "merchant")
    assert pair["role"] == "cashier"

    # The till: same shop as the owner.
    shop_qr = (await client.get("/api/merchant/pay-code", headers=owner)).json()["pay_code"]
    assert (await client.get("/api/merchant/pay-code", headers=cashier)).json()["pay_code"] == shop_qr
    sale = await client.post("/api/merchant/sales", json={"amount": "1500", "idempotency_key": "cashier-sale-1"}, headers=cashier)
    assert sale.status_code == 201, sale.text
    assert (await client.post("/api/merchant/payment-requests", json={"amount": 2000}, headers=cashier)).status_code == 201
    assert (await client.post("/api/merchant/customers/loyalty", json={"phone": "07 12 34 56 78"}, headers=cashier)).status_code == 200
    assert (await client.get("/api/merchant/deals", headers=cashier)).status_code == 200

    # Not the money, the shop's face, or the team.
    for method, url in [("get", "/api/merchant/wave"), ("get", "/api/merchant/staff"), ("get", "/api/merchant/stats")]:
        assert (await getattr(client, method)(url, headers=cashier)).status_code == 403, url
    deal = {"title": "Garba offert", "ends_at": "2030-01-01T00:00:00Z", "discount_percent": 10}
    assert (await client.post("/api/merchant/deals", json=deal, headers=cashier)).status_code == 403
    assert (await client.put("/api/merchant/venue/location", json={"latitude": 5.3, "longitude": -4.0, "accuracy_m": 10}, headers=cashier)).status_code == 403

    # Every sale says who recorded it.
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(models.SaleEvent).where(models.SaleEvent.recorded_by == CASHIER_KEY))).scalar_one()
        assert event.venue_id == sale.json()["venue_id"]

    team = (await client.get("/api/merchant/staff", headers=owner)).json()
    assert [m["name"] for m in team] == ["Caissier (exemple)", "Koffi"]
    assert team[1]["last_login_at"] is not None


@pytest.mark.asyncio
async def test_removing_a_cashier_shuts_them_out_at_once(client):
    owner, _ = await _headers(client, OWNER, "merchant")
    staff_id = (await client.post("/api/merchant/staff", json={"phone": CASHIER}, headers=owner)).json()["id"]
    cashier, pair = await _headers(client, CASHIER, "merchant")

    assert (await client.delete(f"/api/merchant/staff/{staff_id}", headers=owner)).status_code == 204
    # The access token is still unexpired, but the shop link is gone.
    assert (await client.get("/api/merchant/pay-code", headers=cashier)).status_code == 404
    assert (await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401
    assert (await _sign_in(client, CASHIER, "merchant")).status_code == 403
    # Still a customer.
    assert (await _sign_in(client, CASHIER, "customer")).status_code == 200
    assert (await client.delete(f"/api/merchant/staff/{staff_id}", headers=owner)).status_code == 404


@pytest.mark.asyncio
async def test_cashier_rules(client):
    owner, _ = await _headers(client, OWNER, "merchant")
    add = lambda phone, h=owner: client.post("/api/merchant/staff", json={"phone": phone}, headers=h)  # noqa: E731

    assert (await add(OWNER)).status_code == 422
    assert (await add(SEEDED_CASHIER)).status_code == 409  # already on this team
    assert (await add(CASHIER)).status_code == 201

    # Another shop cannot take the same cashier, nor an owner.
    admin = await _admin(client)
    other = {"category": "maquis", "name": "Maquis Autre", "commune": "Abobo", "merchant_phone": "07 55 55 55 55"}
    assert (await client.post("/api/admin/venues", json=other, headers=admin)).status_code == 201
    other_owner, _ = await _headers(client, "07 55 55 55 55", "merchant")
    assert (await add(CASHIER, other_owner)).status_code == 409
    assert (await add(OWNER, other_owner)).status_code == 409

    # A cashier cannot be made an owner while on a team.
    third = {"category": "maquis", "name": "Maquis Trois", "commune": "Yopougon", "merchant_phone": CASHIER}
    r = await client.post("/api/admin/venues", json=third, headers=admin)
    assert r.status_code == 409 and "caissier" in r.json()["detail"]

    # At most ten.
    for i in range(8):
        assert (await add(f"07 66 66 66 {i:02d}")).status_code == 201
    assert (await add("07 66 66 66 99")).status_code == 409


@pytest.mark.asyncio
async def test_seeded_cashier_signs_in_to_the_owners_shop(client):
    _, pair = await _headers(client, SEEDED_CASHIER, "merchant")
    assert pair["role"] == "cashier"


@pytest.mark.asyncio
async def test_field_agent_enrols_shops_and_sees_only_theirs(client):
    agent, pair = await _headers(client, SEEDED_AGENT, "admin")
    assert pair["role"] == "agent"

    shop = {"category": "superette", "name": "Superette Agent", "commune": "Cocody"}
    assert (await client.post("/api/admin/venues", json=shop, headers=agent)).status_code == 422  # owner's number needed
    r = await client.post("/api/admin/venues", json={**shop, "merchant_phone": "07 77 77 77 77"}, headers=agent)
    assert r.status_code == 201, r.text
    venue_id = r.json()["id"]

    mine = (await client.get("/api/agent/venues", headers=agent)).json()
    assert [v["id"] for v in mine] == [venue_id]
    # The new owner signs in straight away.
    assert (await _sign_in(client, "07 77 77 77 77", "merchant")).status_code == 200

    # Nothing else in the admin.
    for url in ["/api/admin/venues", "/api/admin/partner-requests", f"/api/admin/venues/{venue_id}", "/api/admin/users?phone=0700000001"]:
        assert (await client.get(url, headers=agent)).status_code == 403, url

    # Admins see who enrolled it.
    admin = await _admin(client)
    rows = (await client.get("/api/admin/venues?q=Superette Agent", headers=admin)).json()
    assert rows[0]["enrolled_by"] == "+2250700000004"


@pytest.mark.asyncio
async def test_admin_grants_and_removes_the_agent_role(client):
    admin = await _admin(client)
    phone = "07 88 88 88 88"
    assert (await _sign_in(client, phone, "admin")).status_code == 403
    r = await client.post("/api/admin/users/roles", json={"phone": phone, "role": "agent"}, headers=admin)
    assert r.status_code == 200 and "agent" in r.json()["roles"]
    _, pair = await _headers(client, phone, "admin")
    assert pair["role"] == "agent"

    r = await client.post("/api/admin/users/roles/revoke", json={"phone": phone, "role": "agent"}, headers=admin)
    assert r.status_code == 200 and "agent" not in r.json()["roles"]
    assert (await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401
    assert (await _sign_in(client, phone, "admin")).status_code == 403


@pytest.mark.asyncio
async def test_an_owner_who_is_also_an_admin_gets_the_owner_session_in_djassa_pro(client):
    admin = await _admin(client)
    await client.post("/api/admin/users/roles", json={"phone": OWNER, "role": "admin"}, headers=admin)
    assert (await _sign_in(client, OWNER, "merchant")).json()["role"] == "merchant"
    assert (await _sign_in(client, OWNER, "admin")).json()["role"] == "admin"
