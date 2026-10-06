import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app import models
from app.api.customer import utcnow
from app.db import AsyncSessionLocal, Base, engine
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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pay_body(code, **extra):
    return {"pay_code": code, "wallet_provider": "wave", "payer_msisdn": "+2250712345678",
            "idempotency_key": uuid.uuid4().hex, **extra}


@pytest.mark.asyncio
async def test_merchant_qr_is_scanned_confirmed_and_paid(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")

    r = await client.post("/api/merchant/payment-requests", json={"amount": 7500}, headers=merchant)
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["status"] == "open" and req["qr_payload"] == f"hossouko://pay/{req['code']}"

    # Scan: the customer sees the merchant and the amount the MERCHANT set.
    target = (await client.get(f"/api/customer/pay-codes/{req['code']}", headers=customer)).json()
    assert target["amount"] == 7500 and target["name"] == req["venue_name"]

    # Confirm without re-sending the amount: the request's amount is charged.
    paid = (await client.post("/api/customer/payments", json=_pay_body(req["code"]), headers=customer)).json()
    assert paid["status"] == "succeeded" and paid["amount"] == 7500

    # The merchant's polling screen flips to paid.
    status = (await client.get(f"/api/merchant/payment-requests/{req['id']}", headers=merchant)).json()
    assert status["status"] == "paid" and status["wallet_provider"] == "wave" and status["paid_at"]

    # The same QR cannot be paid twice.
    again = await client.post("/api/customer/payments", json=_pay_body(req["code"]), headers=customer)
    assert again.status_code == 409
    assert (await client.get(f"/api/customer/pay-codes/{req['code']}", headers=customer)).status_code == 409


@pytest.mark.asyncio
async def test_tampered_amount_is_refused(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    req = (await client.post("/api/merchant/payment-requests", json={"amount": 7500}, headers=merchant)).json()
    r = await client.post("/api/customer/payments", json=_pay_body(req["code"], amount=100), headers=customer)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_declined_wallet_leaves_the_qr_payable(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    req = (await client.post("/api/merchant/payment-requests", json={"amount": 2000}, headers=merchant)).json()

    declined = (await client.post("/api/customer/payments", headers=customer,
                                  json=_pay_body(req["code"], payer_msisdn="+2250700000000"))).json()
    assert declined["status"] == "failed"
    assert (await client.get(f"/api/merchant/payment-requests/{req['id']}", headers=merchant)).json()["status"] == "open"

    ok = (await client.post("/api/customer/payments", json=_pay_body(req["code"]), headers=customer)).json()
    assert ok["status"] == "succeeded"


@pytest.mark.asyncio
async def test_expired_and_cancelled_requests_cannot_be_paid(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")

    old = (await client.post("/api/merchant/payment-requests", json={"amount": 1000}, headers=merchant)).json()
    async with AsyncSessionLocal() as db:
        await db.execute(update(models.PaymentRequest).where(models.PaymentRequest.id == old["id"])
                         .values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()
    assert (await client.get(f"/api/customer/pay-codes/{old['code']}", headers=customer)).status_code == 410
    assert (await client.get(f"/api/merchant/payment-requests/{old['id']}", headers=merchant)).json()["status"] == "expired"

    live = (await client.post("/api/merchant/payment-requests", json={"amount": 1000}, headers=merchant)).json()
    cancelled = (await client.post(f"/api/merchant/payment-requests/{live['id']}/cancel", headers=merchant)).json()
    assert cancelled["status"] == "cancelled"
    assert (await client.post("/api/customer/payments", json=_pay_body(live["code"]), headers=customer)).status_code == 410


@pytest.mark.asyncio
async def test_only_the_owning_merchant_sees_a_request(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    req = (await client.post("/api/merchant/payment-requests", json={"amount": 1000}, headers=merchant)).json()
    assert (await client.get(f"/api/merchant/payment-requests/{req['id']}", headers=customer)).status_code == 403
    assert (await client.post("/api/merchant/payment-requests", json={"amount": 1000}, headers=customer)).status_code == 403


@pytest.mark.asyncio
async def test_merchant_stats_count_only_money_actually_received(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    before = (await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)).json()

    for amount, phone in ((4000, "+2250712345678"), (6000, "+2250712345678"), (9000, "+2250700000000")):
        req = (await client.post("/api/merchant/payment-requests", json={"amount": amount}, headers=merchant)).json()
        await client.post("/api/customer/payments", json=_pay_body(req["code"], payer_msisdn=phone), headers=customer)

    stats = (await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)).json()
    # The 9000 was declined by the wallet: it is not revenue.
    assert stats["revenue"] - before["revenue"] == 10000
    assert stats["payments"] - before["payments"] == 2
    assert stats["today_revenue"] - before["today_revenue"] == 10000
    assert len(stats["by_day"]) == 7 and sum(d["amount"] for d in stats["by_day"]) == stats["revenue"]
    assert stats["returning_customers"] >= 1  # "client" paid more than once
    assert stats["average_basket"] == stats["revenue"] // stats["payments"]

    assert (await client.get("/api/merchant/stats", headers=customer)).status_code == 403


@pytest.mark.asyncio
async def test_merchant_gets_the_shop_fixed_qr_and_a_customer_can_pay_it(client):
    """The fixed QR for the counter sticker: stable across calls, and payable."""
    merchant = await _auth(client, "demo", "demo123")
    first = await client.get("/api/merchant/pay-code", headers=merchant)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["qr_payload"] == f"hossouko://pay/{body['pay_code']}"
    # The same code every time: the sticker on the counter must keep working.
    again = (await client.get("/api/merchant/pay-code", headers=merchant)).json()
    assert again["pay_code"] == body["pay_code"]

    customer = await _auth(client, "client", "client123")
    target = await client.get(f"/api/customer/pay-codes/{body['pay_code']}", headers=customer)
    assert target.status_code == 200
    assert target.json()["name"] == body["name"]


@pytest.mark.asyncio
async def test_customers_cannot_read_a_merchant_pay_code(client):
    customer = await _auth(client, "client", "client123")
    assert (await client.get("/api/merchant/pay-code", headers=customer)).status_code == 403
