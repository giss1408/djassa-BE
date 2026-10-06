import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app
from app.seed import seed_sample_data


@pytest_asyncio.fixture
async def client():
    # ASGITransport does not run startup events, so do their work here.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _auth(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _payable_maquis(ac, h):
    """A payable maquis, with the code its QR sticker carries."""
    venues = (await ac.get("/api/venues", params={"category": "maquis"}, headers=h)).json()
    venue = next(v for v in venues if v["accepts_payment"])
    admin = await _auth(ac, "admin", "admin123")
    codes = (await ac.get("/api/admin/pay-codes", headers=admin)).json()
    venue["pay_code"] = next(c["pay_code"] for c in codes if c["venue_id"] == venue["id"])
    return venue


@pytest.mark.asyncio
async def test_search_maquis(client):
    h = await _auth(client, "client", "client123")
    r = await client.get("/api/venues", params={"category": "maquis"}, headers=h)
    assert r.status_code == 200
    venues = r.json()
    assert venues and all(v["category"] == "maquis" and v["is_sample"] for v in venues)

    r = await client.get("/api/venues", params={"category": "maquis", "q": "garba"}, headers=h)
    assert [v["commune"] for v in r.json()] == ["Yopougon"]

    r = await client.get("/api/venues", params={"category": "maquis", "commune": "cocody"}, headers=h)
    assert r.json() and all(v["commune"] == "Cocody" for v in r.json())

    r = await client.get("/api/venues", params={"category": "bar"}, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_on_duty_pharmacies_follow_the_rotation(client):
    h = await _auth(client, "client", "client123")
    now = (await client.get("/api/pharmacies/on-duty", headers=h)).json()
    assert now, "the seed puts half the pharmacies on duty this week"
    for p in now:
        start = datetime.fromisoformat(p["duty_starts_at"])
        end = datetime.fromisoformat(p["duty_ends_at"])
        assert start <= datetime.utcnow() < end

    next_week = datetime.utcnow() + timedelta(days=7)
    later = (await client.get("/api/pharmacies/on-duty", params={"at": next_week.isoformat()}, headers=h)).json()
    assert {p["id"] for p in now}.isdisjoint({p["id"] for p in later})


@pytest.mark.asyncio
async def test_only_admin_edits_the_rotation(client):
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    pharmacies = (await client.get("/api/venues", params={"category": "pharmacy"}, headers=admin)).json()
    target = pharmacies[0]["id"]
    far = datetime(2030, 1, 5, 8)
    body = {"starts_at": far.isoformat(), "ends_at": (far + timedelta(days=7)).isoformat()}

    assert (await client.post(f"/api/admin/pharmacies/{target}/duties", json=body, headers=customer)).status_code == 403
    assert (await client.post(f"/api/admin/pharmacies/{target}/duties", json=body, headers=admin)).status_code == 201

    on_duty = (await client.get("/api/pharmacies/on-duty", params={"at": (far + timedelta(days=1)).isoformat()}, headers=customer)).json()
    assert [p["id"] for p in on_duty] == [target]

    backwards = {"starts_at": body["ends_at"], "ends_at": body["starts_at"]}
    assert (await client.post(f"/api/admin/pharmacies/{target}/duties", json=backwards, headers=admin)).status_code == 422


@pytest.mark.asyncio
async def test_payment_earns_points_once_and_retry_is_idempotent(client):
    h = await _auth(client, "client", "client123")
    await client.put("/api/customer/loyalty-consent", json={"consent_version": "test"}, headers=h)
    venue = await _payable_maquis(client, h)
    before = (await client.get(f"/api/venues/{venue['id']}", headers=h)).json()["my_points"]

    body = {
        "pay_code": venue["pay_code"],
        "amount": 5000,
        "wallet_provider": "wave",
        "payer_msisdn": "+225 07 12 34 56 78",
        "idempotency_key": uuid.uuid4().hex,
    }
    r = await client.post("/api/customer/payments", json=body, headers=h)
    assert r.status_code == 201, r.text
    paid = r.json()
    expected = 50 * venue["points_per_100"]
    assert paid["status"] == "succeeded" and paid["points_awarded"] == expected
    assert paid["provider_reference"].startswith("FAKE-")

    # Same key again (the phone lost the first response): same payment, no new points.
    again = (await client.post("/api/customer/payments", json=body, headers=h)).json()
    assert again["id"] == paid["id"]
    after = (await client.get(f"/api/venues/{venue['id']}", headers=h)).json()["my_points"]
    assert after == before + expected

    history = (await client.get("/api/customer/payments", headers=h)).json()
    assert history[0]["id"] == paid["id"]


@pytest.mark.asyncio
async def test_declined_payment_earns_nothing(client):
    h = await _auth(client, "client", "client123")
    venue = await _payable_maquis(client, h)
    body = {
        "pay_code": venue["pay_code"],
        "amount": 3000,
        "wallet_provider": "orange",
        "payer_msisdn": "+2250700000000",  # the fake provider declines *0000
        "idempotency_key": uuid.uuid4().hex,
    }
    paid = (await client.post("/api/customer/payments", json=body, headers=h)).json()
    assert paid["status"] == "failed" and paid["points_awarded"] == 0 and paid["failure_reason"]


@pytest.mark.asyncio
async def test_scanned_code_resolves_to_the_server_side_merchant(client):
    h = await _auth(client, "client", "client123")
    venue = await _payable_maquis(client, h)
    r = await client.get(f"/api/customer/pay-codes/{venue['pay_code']}", headers=h)
    assert r.status_code == 200
    target = r.json()
    assert target["venue_id"] == venue["id"] and target["name"] == venue["name"]
    # Only the last digits of the merchant's wallet are revealed.
    assert target["payout_account_masked"].startswith("\u2022") and len(target["payout_account_masked"]) == 8

    assert (await client.get("/api/customer/pay-codes/NOTACODE00", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_payment_guards(client):
    h = await _auth(client, "client", "client123")
    merchant = await _auth(client, "demo", "demo123")
    venue = await _payable_maquis(client, h)
    body = {"pay_code": venue["pay_code"], "amount": 1000, "wallet_provider": "mtn",
            "payer_msisdn": "+2250500000009", "idempotency_key": uuid.uuid4().hex}

    # Unknown code, amount below the floor, and a non-customer account: all refused.
    assert (await client.post("/api/customer/payments", json={**body, "pay_code": "NOTACODE00"}, headers=h)).status_code == 404
    assert (await client.post("/api/customer/payments", json={**body, "amount": 50}, headers=h)).status_code == 422
    assert (await client.post("/api/customer/payments", json=body, headers=merchant)).status_code == 403
    # No pay code at all: paying requires having scanned the QR.
    no_code = {k: v for k, v in body.items() if k != "pay_code"}
    assert (await client.post("/api/customer/payments", json=no_code, headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_rotated_code_stops_working_between_scan_and_pay(client):
    h = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    venue = await _payable_maquis(client, h)
    old = venue["pay_code"]
    assert (await client.get(f"/api/customer/pay-codes/{old}", headers=h)).status_code == 200

    rotated = (await client.post(f"/api/admin/venues/{venue['id']}/pay-code", headers=admin)).json()
    assert rotated["pay_code"] != old and rotated["qr_payload"] == f"hossouko://pay/{rotated['pay_code']}"

    body = {"pay_code": old, "amount": 1000, "wallet_provider": "wave",
            "payer_msisdn": "+2250712345678", "idempotency_key": uuid.uuid4().hex}
    assert (await client.post("/api/customer/payments", json=body, headers=h)).status_code == 404
    ok = await client.post("/api/customer/payments", json={**body, "pay_code": rotated["pay_code"]}, headers=h)
    assert ok.status_code == 201 and ok.json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_redeem_reward_spends_venue_points(client):
    h = await _auth(client, "client", "client123")
    await client.put("/api/customer/loyalty-consent", json={"consent_version": "test"}, headers=h)
    venue = await _payable_maquis(client, h)
    detail = (await client.get(f"/api/venues/{venue['id']}", headers=h)).json()
    reward = detail["rewards"][0]

    # Earn enough at this venue.
    need = max(0, reward["cost_points"] - detail["my_points"])
    amount = max(100, -(-need // venue["points_per_100"]) * 100)
    await client.post("/api/customer/payments", headers=h, json={
        "pay_code": venue["pay_code"], "amount": amount, "wallet_provider": "wave",
        "payer_msisdn": "+2250712345678", "idempotency_key": uuid.uuid4().hex})
    balance = (await client.get(f"/api/venues/{venue['id']}", headers=h)).json()["my_points"]

    r = await client.post("/api/customer/loyalty/redeem", json={"reward_id": reward["id"]}, headers=h)
    assert r.status_code == 201, r.text
    out = r.json()
    assert len(out["voucher_code"]) == 6
    assert out["remaining_points"] == balance - reward["cost_points"]

    loyalty = (await client.get("/api/customer/loyalty", headers=h)).json()
    assert loyalty["history"][0]["voucher_code"] == out["voucher_code"]
    assert loyalty["total_points"] == sum(v["points"] for v in loyalty["venues"])

    # A reward costing more than the remaining balance is refused.
    pricey = max(detail["rewards"], key=lambda x: x["cost_points"])
    while (await client.get(f"/api/venues/{venue['id']}", headers=h)).json()["my_points"] >= pricey["cost_points"]:
        await client.post("/api/customer/loyalty/redeem", json={"reward_id": pricey["id"]}, headers=h)
    r = await client.post("/api/customer/loyalty/redeem", json={"reward_id": pricey["id"]}, headers=h)
    assert r.status_code == 409


async def _pay_once(client, h, venue, amount=5000):
    return await client.post("/api/customer/payments", headers=h, json={
        "pay_code": venue["pay_code"], "amount": amount, "wallet_provider": "wave",
        "payer_msisdn": "+2250712345678", "idempotency_key": uuid.uuid4().hex})


@pytest.mark.asyncio
async def test_no_consent_no_points_and_withdrawing_erases_them(client):
    h = await _auth(client, "client", "client123")
    venue = await _payable_maquis(client, h)
    # This file shares one database; earlier tests may have given consent.
    await client.delete("/api/customer/loyalty-consent", headers=h)
    assert (await client.get("/api/customer/loyalty-consent", headers=h)).json()["active"] is False
    r = await _pay_once(client, h, venue)
    assert r.status_code == 201 and r.json()["points_awarded"] == 0

    given = (await client.put("/api/customer/loyalty-consent", json={"consent_version": "fidelite-2026-10"}, headers=h)).json()
    assert given["active"] is True and given["source"] == "app"
    assert (await _pay_once(client, h, venue)).json()["points_awarded"] > 0
    total = (await client.get("/api/customer/loyalty", headers=h)).json()["total_points"]
    assert total > 0

    gone = await client.delete("/api/customer/loyalty-consent", headers=h)
    assert gone.status_code == 200 and gone.json()["points_erased"] == total
    assert (await client.get("/api/customer/loyalty", headers=h)).json()["total_points"] == 0
    assert (await client.get("/api/customer/loyalty-consent", headers=h)).json()["active"] is False
    assert (await _pay_once(client, h, venue)).json()["points_awarded"] == 0
