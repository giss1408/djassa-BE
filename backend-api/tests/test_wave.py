"""Wave option B: each merchant connects their own Wave Business account.

Wave has no sandbox, so a small in-memory Wave stands in for api.wave.com
(httpx.MockTransport), with the request and event shapes from docs.wave.com.
"""

import json
import time
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data
from app.api.customer import utcnow
from app.services import wave

GOOD_KEY = "wave_ci_prod_" + "k" * 40
SECRET = "wave_ci_WHS_" + "s" * 30


class FakeWave:
    """Just enough of api.wave.com for a checkout's life cycle."""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.created: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != f"Bearer {GOOD_KEY}":
            return httpx.Response(401, json={"code": "no-matching-api-key"})
        path = request.url.path
        if request.method == "GET" and path == "/v1/checkout/sessions/search":
            return httpx.Response(200, json={"result": []})
        if request.method == "POST" and path == "/v1/checkout/sessions":
            body = json.loads(request.content)
            self.created.append(body)
            sid = f"cos-{uuid.uuid4().hex[:10]}"
            self.sessions[sid] = {
                "id": sid,
                "amount": body["amount"],
                "currency": body["currency"],
                "client_reference": body["client_reference"],
                "checkout_status": "open",
                "payment_status": "processing",
                "wave_launch_url": f"https://pay.wave.com/c/{sid}",
            }
            return httpx.Response(200, json=self.sessions[sid])
        if request.method == "GET" and path.startswith("/v1/checkout/sessions/"):
            sid = path.rsplit("/", 1)[1]
            return httpx.Response(200, json=self.sessions[sid]) if sid in self.sessions else httpx.Response(404)
        return httpx.Response(404)

    def pay(self, sid: str, txn: str = "T_ABC123") -> dict:
        s = self.sessions[sid]
        s.update(checkout_status="complete", payment_status="succeeded", transaction_id=txn)
        return s


@pytest.fixture
def fake_wave(monkeypatch):
    fake = FakeWave()
    monkeypatch.setattr(
        wave, "client_for", lambda key: wave.WaveClient(key, transport=httpx.MockTransport(fake.handler))
    )
    return fake


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
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _connect(ac, merchant, **extra):
    body = {"api_key": GOOD_KEY, "webhook_secret": SECRET, **extra}
    return await ac.put("/api/merchant/wave", json=body, headers=merchant)


async def _pay(ac, merchant, customer, amount=2500, msisdn="07 12 34 56 78"):
    code = (await ac.get("/api/merchant/pay-code", headers=merchant)).json()["pay_code"]
    return await ac.post(
        "/api/customer/payments",
        json={"pay_code": code, "amount": amount, "wallet_provider": "wave", "payer_msisdn": msisdn,
              "idempotency_key": uuid.uuid4().hex},
        headers=customer,
    )


async def _post_event(ac, url_path, event, secret=SECRET, ts=None):
    body = json.dumps(event).encode()
    header = wave.sign(secret, body, ts or int(time.time()))
    return await ac.post(url_path, content=body, headers={"Wave-Signature": header, "Content-Type": "application/json"})


def _hook_path(connected):
    return "/" + connected["webhook_url"].split("/", 3)[3]


# --- Signatures ---------------------------------------------------------------


def test_signature_accepts_wave_format_and_rejects_tampering():
    body = b'{"type":"x"}'
    now = 1_700_000_000
    header = wave.sign(SECRET, body, now)
    assert wave.verify_signature(SECRET, header, body, now=now)
    assert not wave.verify_signature(SECRET, header, body + b" ", now=now)
    assert not wave.verify_signature("other-secret", header, body, now=now)
    # Replayed after the five-minute window.
    assert not wave.verify_signature(SECRET, header, body, now=now + 301)
    # During a secret rotation Wave sends several v1 values; one match is enough.
    rotated = header.replace("t=", "t=", 1) + ",v1=deadbeef"
    assert wave.verify_signature(SECRET, rotated, body, now=now)
    assert not wave.verify_signature(SECRET, None, body, now=now)


def test_amounts_are_whole_francs():
    assert wave.parse_amount("2500") == 2500
    assert wave.parse_amount("2500.00") == 2500
    assert wave.parse_amount("2500.5") is None
    assert wave.parse_amount("-1") is None
    assert wave.parse_amount(None) is None


# --- Connection -------------------------------------------------------------


async def _consent(phone_e164: str):
    """The payer agreed to loyalty in Djassa (app or counter) beforehand."""
    async with AsyncSessionLocal() as db:
        db.add(models.LoyaltyConsent(customer_id=f"tel:{phone_e164}", source="app", consent_version="test", granted_at=utcnow()))
        await db.commit()


@pytest.mark.asyncio
async def test_merchant_connects_their_wave_and_the_key_is_never_returned(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    assert (await client.get("/api/merchant/wave", headers=merchant)).json()["connected"] is False

    r = await _connect(client, merchant)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] and body["webhook_configured"]
    assert body["api_key_hint"] == "…kkkk"
    assert "/webhooks/wave/" in body["webhook_url"]
    assert GOOD_KEY not in r.text and SECRET not in r.text

    async with AsyncSessionLocal() as db:
        account = (await db.execute(select(models.WaveAccount))).scalar_one()
        assert GOOD_KEY not in account.api_key_sealed  # sealed at rest

    assert (await client.delete("/api/merchant/wave", headers=merchant)).status_code == 204
    assert (await client.get("/api/merchant/wave", headers=merchant)).json()["connected"] is False


@pytest.mark.asyncio
async def test_a_wrong_key_is_refused_at_connection(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    r = await _connect(client, merchant, api_key="wave_ci_prod_" + "x" * 40)
    assert r.status_code == 422
    assert "refusee" in r.json()["detail"]


# --- Checkout payments ------------------------------------------------------


@pytest.mark.asyncio
async def test_wave_checkout_is_created_with_the_merchants_key_and_settled_by_webhook(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await client.put("/api/customer/loyalty-consent", json={"consent_version": "test"}, headers=customer)
    connected = (await _connect(client, merchant)).json()

    r = await _pay(client, merchant, customer)
    assert r.status_code == 201, r.text
    payment = r.json()
    assert payment["status"] == "pending"
    assert payment["checkout_url"].startswith("https://pay.wave.com/c/")
    sent = fake_wave.created[0]
    assert sent["amount"] == "2500" and sent["currency"] == "XOF"
    # Only the customer's own wallet can pay it.
    assert sent["restrict_payer_mobile"] == "+2250712345678"
    assert sent["success_url"].endswith("/wave/return?result=ok")

    session = fake_wave.pay(payment["provider_reference"])
    event = {"id": "EV_1", "type": "checkout.session.completed", "data": session}
    hook = _hook_path(connected)
    assert (await _post_event(client, hook, event)).status_code == 200
    # A replay of the same event grants nothing more.
    assert (await _post_event(client, hook, event)).status_code == 200

    done = (await client.get(f"/api/customer/payments/{payment['id']}", headers=customer)).json()
    assert done["status"] == "succeeded"
    assert done["points_awarded"] == 50  # the demo venue gives 2 points per 100 F
    assert done["checkout_url"] is None
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(models.SaleEvent).where(models.SaleEvent.payment_id == payment["id"]))).scalars().all()
        assert len(events) == 1 and events[0].source == "mobile_money_confirmed"
        entries = (await db.execute(select(models.LoyaltyEntry).where(models.LoyaltyEntry.payment_id == payment["id"]))).scalars().all()
        assert len(entries) == 1


@pytest.mark.asyncio
async def test_a_late_webhook_is_covered_by_the_status_refresh(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await _connect(client, merchant, webhook_secret=None)
    payment = (await _pay(client, merchant, customer)).json()

    still = (await client.get(f"/api/customer/payments/{payment['id']}", headers=customer)).json()
    assert still["status"] == "pending"

    fake_wave.pay(payment["provider_reference"])
    done = (await client.get(f"/api/customer/payments/{payment['id']}", headers=customer)).json()
    assert done["status"] == "succeeded"


@pytest.mark.asyncio
async def test_a_failed_checkout_leaves_nothing_granted(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    connected = (await _connect(client, merchant)).json()
    payment = (await _pay(client, merchant, customer)).json()

    event = {
        "id": "EV_2",
        "type": "checkout.session.payment_failed",
        "data": {
            "id": payment["provider_reference"],
            "client_reference": fake_wave.created[0]["client_reference"],
            "last_payment_error": {"code": "insufficient-funds", "message": "Solde insuffisant"},
        },
    }
    assert (await _post_event(client, _hook_path(connected), event)).status_code == 200
    done = (await client.get(f"/api/customer/payments/{payment['id']}", headers=customer)).json()
    assert done["status"] == "failed"
    assert done["failure_reason"] == "Solde insuffisant"
    assert done["points_awarded"] == 0


@pytest.mark.asyncio
async def test_unsigned_or_wrongly_signed_events_are_refused(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    connected = (await _connect(client, merchant)).json()
    hook = _hook_path(connected)
    event = {"id": "EV_3", "type": "merchant.payment_received", "data": {}}
    assert (await client.post(hook, json=event)).status_code == 401
    assert (await _post_event(client, hook, event, secret="not-the-secret")).status_code == 401
    assert (await _post_event(client, "/webhooks/wave/unknown-token", event)).status_code == 404


# --- Payments outside Djassa ---------------------------------------------


@pytest.mark.asyncio
async def test_a_plain_wave_payment_to_the_merchant_earns_points_on_the_phone(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    await _consent("+2250701020304")
    connected = (await _connect(client, merchant)).json()
    event = {
        "id": "EV_4",
        "type": "merchant.payment_received",
        "data": {"id": "T_DIRECT1", "amount": "3000", "currency": "XOF", "fee": "0",
                 "sender_mobile": "+2250701020304", "merchant_name": "Maquis"},
    }
    hook = _hook_path(connected)
    assert (await _post_event(client, hook, event)).status_code == 200
    assert (await _post_event(client, hook, event)).status_code == 200  # replay

    r = await client.post("/api/merchant/customers/loyalty", json={"phone": "07 01 02 03 04"}, headers=merchant)
    assert r.status_code == 200, r.text
    assert r.json()["points"] == 60
    async with AsyncSessionLocal() as db:
        sale = (await db.execute(select(models.SaleEvent).where(models.SaleEvent.idempotency_key == "wave:T_DIRECT1"))).scalar_one()
        assert sale.source == "mobile_money_confirmed"


@pytest.mark.asyncio
async def test_a_checkout_payment_is_not_counted_twice_as_a_plain_payment(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    connected = (await _connect(client, merchant)).json()
    payment = (await _pay(client, merchant, customer)).json()
    hook = _hook_path(connected)
    # Wave may report the same money as a merchant payment, before or after the checkout event.
    received = {"id": "EV_5", "type": "merchant.payment_received",
                "data": {"id": "T_SAME", "amount": "2500", "currency": "XOF", "sender_mobile": "+2250712345678"}}
    assert (await _post_event(client, hook, received)).status_code == 200
    session = fake_wave.pay(payment["provider_reference"], txn="T_SAME")
    completed = {"id": "EV_6", "type": "checkout.session.completed", "data": session}
    assert (await _post_event(client, hook, completed)).status_code == 200
    assert (await _post_event(client, hook, received)).status_code == 200

    async with AsyncSessionLocal() as db:
        venue_id = (await db.execute(select(models.CustomerPayment.venue_id))).scalar_one()
        sales = (await db.execute(select(models.SaleEvent).where(
            models.SaleEvent.venue_id == venue_id, models.SaleEvent.source == "mobile_money_confirmed"
        ))).scalars().all()
        assert len(sales) == 1


# --- Provider selection -----------------------------------------------------


@pytest.mark.asyncio
async def test_without_a_connected_account_production_refuses_wave(client, fake_wave, monkeypatch):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    code = (await client.get("/api/merchant/pay-code", headers=merchant)).json()["pay_code"]
    monkeypatch.setenv("MOBILE_MONEY_PROVIDER", "wave")
    monkeypatch.setenv("DJASSA_ENV", "production")
    monkeypatch.setenv("DJASSA_ENCRYPTION_KEY", "test-key")
    r = await client.post(
        "/api/customer/payments",
        json={"pay_code": code, "amount": 1000, "wallet_provider": "wave", "payer_msisdn": "0712345678",
              "idempotency_key": uuid.uuid4().hex},
        headers=customer,
    )
    assert r.status_code == 422
    assert "Payez au comptoir" in r.json()["detail"]
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.CustomerPayment))).first() is None


# --- Points only: no payment key --------------------------------------------


@pytest.mark.asyncio
async def test_points_only_needs_no_key_and_still_earns_points(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    await _consent("+2250701020304")
    # An empty body creates the webhook address first, before Wave gives the secret.
    started = (await client.put("/api/merchant/wave", json={}, headers=merchant)).json()
    assert started["connected"] is True
    assert started["payments_enabled"] is False
    assert started["webhook_configured"] is False
    assert started["webhook_url"]

    connected = (await client.put("/api/merchant/wave", json={"webhook_secret": SECRET}, headers=merchant)).json()
    assert connected["webhook_configured"] is True
    assert connected["payments_enabled"] is False
    assert connected["webhook_url"] == started["webhook_url"]
    async with AsyncSessionLocal() as db:
        account = (await db.execute(select(models.WaveAccount))).scalar_one()
        assert account.api_key_sealed is None

    event = {"id": "EV_P1", "type": "merchant.payment_received",
             "data": {"id": "T_POINTS1", "amount": "1500", "currency": "XOF", "sender_mobile": "+2250701020304"}}
    assert (await _post_event(client, _hook_path(connected), event)).status_code == 200
    r = await client.post("/api/merchant/customers/loyalty", json={"phone": "07 01 02 03 04"}, headers=merchant)
    assert r.json()["points"] == 30


@pytest.mark.asyncio
async def test_a_key_can_be_added_later_without_touching_the_secret(client, fake_wave):
    merchant = await _auth(client, "demo", "demo123")
    await client.put("/api/merchant/wave", json={"webhook_secret": SECRET}, headers=merchant)
    r = (await client.put("/api/merchant/wave", json={"api_key": GOOD_KEY}, headers=merchant)).json()
    assert r["payments_enabled"] is True
    assert r["webhook_configured"] is True


@pytest.mark.asyncio
async def test_points_only_shop_sends_wave_payers_to_the_shop_qr(client, fake_wave, monkeypatch):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await client.put("/api/merchant/wave", json={"webhook_secret": SECRET}, headers=merchant)
    code = (await client.get("/api/merchant/pay-code", headers=merchant)).json()["pay_code"]
    monkeypatch.setenv("DJASSA_ENV", "production")
    monkeypatch.setenv("DJASSA_ENCRYPTION_KEY", "test-key")
    r = await client.post(
        "/api/customer/payments",
        json={"pay_code": code, "amount": 1000, "wallet_provider": "wave", "payer_msisdn": "0712345678",
              "idempotency_key": uuid.uuid4().hex},
        headers=customer,
    )
    assert r.status_code == 422
    assert "QR Wave du commerce" in r.json()["detail"]
    assert fake_wave.created == []


@pytest.mark.asyncio
async def test_a_payer_who_never_agreed_is_recorded_anonymously(client, fake_wave):
    """Wave hands over the sender's number without the payer asking Djassa for
    anything: the sale counts for the merchant, but the number is not kept."""
    merchant = await _auth(client, "demo", "demo123")
    connected = (await client.put("/api/merchant/wave", json={"webhook_secret": SECRET}, headers=merchant)).json()
    event = {"id": "EV_ANON", "type": "merchant.payment_received",
             "data": {"id": "T_ANON1", "amount": "1500", "currency": "XOF", "sender_mobile": "+2250709090909"}}
    assert (await _post_event(client, _hook_path(connected), event)).status_code == 200

    async with AsyncSessionLocal() as db:
        sale = (await db.execute(select(models.SaleEvent).where(models.SaleEvent.idempotency_key == "wave:T_ANON1"))).scalar_one()
        assert sale.customer_id is None and sale.loyalty_entry_id is None
        assert (await db.execute(select(models.LoyaltyEntry).where(models.LoyaltyEntry.customer_id == "tel:+2250709090909"))).first() is None
