"""Deleting an account (Google Play's account deletion requirement).

A customer deletes their own account at once: what identifies them is erased,
what is also the merchants' record stays under a key that names nobody, so a
shop's history and totals do not change. Merchants and cashiers ask; an admin
deletes once the person owns no shop.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from app.services import account_delete

PHONE = "07 12 34 56 78"
E164 = "+2250712345678"
KEY = "tel:" + E164


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setenv("OTP_SENDER", "console")
    monkeypatch.setenv("OTP_DEV_ECHO", "1")
    monkeypatch.delenv("FIDELIA_ENV", raising=False)
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


async def _age_codes():
    from datetime import timedelta

    async with AsyncSessionLocal() as db:
        for c in (await db.execute(select(models.OtpChallenge))).scalars():
            c.created_at -= timedelta(seconds=400)
        await db.commit()


async def _sign_in(ac, phone=PHONE, app_name="customer"):
    await _age_codes()
    code = (await ac.post("/api/auth/otp/request", json={"phone": phone, "app": app_name})).json()["dev_code"]
    r = await ac.post("/api/auth/otp/verify", json={"phone": phone, "code": code, "app": app_name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _password(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _count(model, *where):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def _earn_and_pay(ac, customer):
    """Points from a counter sale, and a Wave payment from the app."""
    merchant = await _password(ac, "demo", "demo123")
    sale = await ac.post(
        "/api/merchant/sales",
        json={"amount": "5000", "idempotency_key": "del-sale-0001", "customer_phone": PHONE, "customer_consent": True},
        headers=merchant,
    )
    assert sale.status_code == 201, sale.text
    req = (await ac.post("/api/merchant/payment-requests", json={"amount": 2000}, headers=merchant)).json()
    paid = await ac.post(
        "/api/customer/payments",
        json={"pay_code": req["code"], "wallet_provider": "wave", "payer_msisdn": E164, "idempotency_key": "del-pay-0001"},
        headers=customer,
    )
    assert paid.status_code == 201, paid.text


def test_every_column_that_names_a_person_is_classified():
    assert account_delete.unclassified() == []


@pytest.mark.asyncio
async def test_a_customer_deletes_their_account_and_the_shop_keeps_its_figures(client):
    customer = await _sign_in(client)
    await _earn_and_pay(client, customer)
    sales_before = await _count(models.SaleEvent)
    assert await _count(models.LoyaltyEntry, models.LoyaltyEntry.customer_id == KEY) > 0

    r = await client.delete("/api/account", headers=customer)
    assert r.status_code == 200, r.text

    # The person is gone...
    assert await _count(models.User, models.User.phone_e164 == E164) == 0
    assert await _count(models.LoyaltyEntry, models.LoyaltyEntry.customer_id == KEY) == 0
    assert await _count(models.LoyaltyConsent, models.LoyaltyConsent.customer_id == KEY) == 0
    assert await _count(models.SaleEvent, models.SaleEvent.customer_id == KEY) == 0
    assert await _count(models.CustomerPayment, models.CustomerPayment.customer_id == KEY) == 0
    assert await _count(models.CustomerPayment, models.CustomerPayment.payer_msisdn == E164) == 0
    assert await _count(models.OtpChallenge, models.OtpChallenge.phone_e164 == E164) == 0
    # ...the shop's records are not.
    assert await _count(models.SaleEvent) == sales_before
    assert await _count(models.CustomerPayment, models.CustomerPayment.customer_id.like("deleted:%")) == 1

    # Signing in again opens a new, empty account.
    again = await _sign_in(client)
    assert (await client.get("/api/customer/loyalty", headers=again)).json()["total_points"] == 0


@pytest.mark.asyncio
async def test_a_shop_number_is_sent_to_the_team(client):
    # The seeded merchant's number, signed in to the customer app.
    as_customer = await _sign_in(client, "07 00 00 00 02")
    r = await client.delete("/api/account", headers=as_customer)
    assert r.status_code == 409
    assert "Fidelia Pro" in r.json()["detail"]
    merchant = await _sign_in(client, "07 00 00 00 02", "merchant")
    assert (await client.delete("/api/account", headers=merchant)).status_code == 403


@pytest.mark.asyncio
async def test_an_unfinished_layaway_blocks_deletion(client):
    customer = await _sign_in(client)
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
        from datetime import datetime

        db.add(models.LayawayPlan(
            venue_id=venue.id, customer_id=KEY, item="Radio", price=10000, currency="XOF", status="open",
            due_by=datetime(2027, 1, 1), terms_version="v", created_by="demo", created_at=datetime(2026, 10, 1),
        ))
        await db.commit()
    r = await client.delete("/api/account", headers=customer)
    assert r.status_code == 409
    assert "plusieurs fois" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_cashier_asks_and_an_admin_deletes(client):
    cashier = await _sign_in(client, "07 00 00 00 03", "merchant")
    first = await client.post("/api/account/deletion-request", json={"reason": "Je quitte le commerce"}, headers=cashier)
    again = await client.post("/api/account/deletion-request", json={}, headers=cashier)
    assert first.status_code == again.status_code == 202
    assert first.json()["id"] == again.json()["id"]

    admin = await _sign_in(client, "07 00 00 00 09", "admin")
    pending = (await client.get("/api/admin/deletion-requests", headers=admin)).json()
    assert [(p["phone"], p["role"], p["reason"]) for p in pending] == [("+2250700000003", "cashier", "Je quitte le commerce")]
    assert pending[0]["venue_name"]

    done = await client.post(f"/api/admin/deletion-requests/{pending[0]['id']}/done", json={"note": "ok"}, headers=admin)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"
    assert await _count(models.User, models.User.phone_e164 == "+2250700000003") == 0
    cashier_key = "tel:+2250700000003"
    assert await _count(models.VenueStaff, models.VenueStaff.user_key == cashier_key) == 0
    assert await _count(models.SaleEvent, models.SaleEvent.recorded_by == cashier_key) == 0


@pytest.mark.asyncio
async def test_an_owner_is_deleted_only_once_the_shop_is_handed_over(client):
    owner = await _sign_in(client, "07 00 00 00 02", "merchant")
    assert (await client.post("/api/account/deletion-request", json={}, headers=owner)).status_code == 202
    admin = await _sign_in(client, "07 00 00 00 09", "admin")
    request = (await client.get("/api/admin/deletion-requests", headers=admin)).json()[0]
    r = await client.post(f"/api/admin/deletion-requests/{request['id']}/done", json={}, headers=admin)
    assert r.status_code == 409
    assert "commerce" in r.json()["detail"]
    assert await _count(models.User, models.User.phone_e164 == "+2250700000002") == 1

    rejected = await client.post(f"/api/admin/deletion-requests/{request['id']}/reject", json={"note": "doublon"}, headers=admin)
    assert rejected.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_only_admins_see_and_decide_requests(client):
    customer = await _sign_in(client)
    assert (await client.get("/api/admin/deletion-requests", headers=customer)).status_code == 403
