"""Subscriptions and billing: the Phase 1 exit gate ("merchants pay or renew")
has to be answerable from the database, and the recording habit must never be
behind the paywall.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.entitlements import STARTER_STATS_DAYS
from app.db import Base, engine
from app.main import app
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
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _my_venue_id(ac, merchant):
    r = await ac.get("/api/merchant/subscription", headers=merchant)
    assert r.status_code == 200, r.text
    return r.json()["venue_id"]


@pytest.mark.asyncio
async def test_a_venue_with_no_subscription_reads_as_starter(client):
    merchant = await _auth(client, "demo", "demo123")
    sub = (await client.get("/api/merchant/subscription", headers=merchant)).json()
    assert sub["plan"] == "starter"
    assert sub["status"] == "none"
    assert sub["max_stats_days"] == STARTER_STATS_DAYS
    assert sub["features"] == []
    assert (await client.get("/api/merchant/billing/events", headers=merchant)).json() == []


@pytest.mark.asyncio
async def test_recording_and_loyalty_are_never_gated(client):
    """The one thing a plan must not touch: the transaction-recording habit."""
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await client.put("/api/customer/loyalty-consent", json={"consent_version": "test"}, headers=customer)

    # Starter merchant, no subscription at all.
    r = await client.post("/api/merchant/payment-requests", json={"amount": 2000}, headers=merchant)
    assert r.status_code == 201, r.text
    code = r.json()["code"]

    paid = await client.post(
        "/api/customer/payments",
        json={
            "pay_code": code,
            "wallet_provider": "wave",
            "payer_msisdn": "+2250700000099",
            "idempotency_key": "billing-test-key-1",
        },
        headers=customer,
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["status"] == "succeeded"
    assert paid.json()["points_awarded"] > 0, "points still accrue on the free plan"

    # And the short stats window still works.
    assert (await client.get("/api/merchant/stats", params={"days": STARTER_STATS_DAYS}, headers=merchant)).status_code == 200

    # Publishing a bon plan is not gated either.
    from datetime import datetime, timedelta, timezone

    ends = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert (
        await client.post(
            "/api/merchant/deals",
            json={"title": "Gratuit quand meme", "discount_percent": 10, "ends_at": ends},
            headers=merchant,
        )
    ).status_code == 201


@pytest.mark.asyncio
async def test_long_stats_window_is_refused_on_starter_and_allowed_on_growth(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    venue_id = await _my_venue_id(client, merchant)

    refused = await client.get("/api/merchant/stats", params={"days": 90}, headers=merchant)
    assert refused.status_code == 402
    assert str(STARTER_STATS_DAYS) in refused.json()["detail"]

    r = await client.put(
        f"/api/admin/venues/{venue_id}/subscription",
        json={"plan": "growth", "amount": 7000},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "growth" and r.json()["max_stats_days"] is None
    assert "long_stats" in r.json()["features"]

    assert (await client.get("/api/merchant/stats", params={"days": 90}, headers=merchant)).status_code == 200


@pytest.mark.asyncio
async def test_a_merchant_cannot_change_their_own_plan(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    venue_id = await _my_venue_id(client, merchant)
    body = {"plan": "network", "amount": 0}

    assert (await client.put(f"/api/admin/venues/{venue_id}/subscription", json=body, headers=merchant)).status_code == 403
    assert (await client.put(f"/api/admin/venues/{venue_id}/subscription", json=body, headers=customer)).status_code == 403
    assert (await client.get("/api/admin/subscriptions", headers=merchant)).status_code == 403
    assert (await client.get("/api/admin/revenue", headers=merchant)).status_code == 403

    # Still starter.
    assert (await client.get("/api/merchant/subscription", headers=merchant)).json()["plan"] == "starter"


@pytest.mark.asyncio
async def test_paying_reactivates_a_past_due_account_and_appends_an_event(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    venue_id = await _my_venue_id(client, merchant)

    await client.put(
        f"/api/admin/venues/{venue_id}/subscription", json={"plan": "growth", "amount": 7000}, headers=admin
    )
    lapsed = await client.post(f"/api/admin/venues/{venue_id}/subscription/unpaid", headers=admin)
    assert lapsed.status_code == 200 and lapsed.json()["status"] == "past_due"

    # Lapsing does not downgrade what they can read: chasing payment is a
    # commercial matter, not a reason to cut off a merchant's own history.
    assert lapsed.json()["max_stats_days"] is None

    paid = await client.post(
        f"/api/admin/venues/{venue_id}/subscription/payments",
        json={"payment_reference": "WAVE-77", "note": "especes au comptoir"},
        headers=admin,
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "active"

    events = (await client.get("/api/merchant/billing/events", headers=merchant)).json()
    kinds = [e["kind"] for e in events]
    assert "paid" in kinds and "failed" in kinds and "invoice_due" in kinds
    settled = next(e for e in events if e["kind"] == "paid")
    assert settled["amount"] == 7000 and settled["payment_reference"] == "WAVE-77"


@pytest.mark.asyncio
async def test_a_late_payment_does_not_extend_the_period_for_free(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    venue_id = await _my_venue_id(client, merchant)
    await client.put(
        f"/api/admin/venues/{venue_id}/subscription", json={"plan": "growth", "amount": 7000}, headers=admin
    )
    first_end = (await client.get("/api/merchant/subscription", headers=merchant)).json()["current_period_end"]

    rolled = await client.post(f"/api/admin/venues/{venue_id}/subscription/payments", json={}, headers=admin)
    assert rolled.json()["current_period_start"] == first_end, "the new period starts where the old one ended"
    assert rolled.json()["current_period_end"] > first_end


@pytest.mark.asyncio
async def test_revenue_summary_answers_the_phase_one_gate(client):
    admin = await _auth(client, "admin", "admin123")
    merchant = await _auth(client, "demo", "demo123")
    venue_id = await _my_venue_id(client, merchant)

    empty = (await client.get("/api/admin/revenue", headers=admin)).json()
    assert empty["mrr"] == 0 and empty["active_paying_outlets"] == 0

    await client.put(
        f"/api/admin/venues/{venue_id}/subscription", json={"plan": "growth", "amount": 7000}, headers=admin
    )
    # Trialing is not revenue yet: counting it would overstate the one number
    # the scale decision rests on.
    trialing = (await client.get("/api/admin/revenue", headers=admin)).json()
    assert trialing["mrr"] == 0
    assert trialing["unpaid_invoices"] == 1 and trialing["unpaid_amount"] == 7000

    await client.post(f"/api/admin/venues/{venue_id}/subscription/payments", json={}, headers=admin)
    paid = (await client.get("/api/admin/revenue", headers=admin)).json()
    assert paid["mrr"] == 7000 and paid["active_paying_outlets"] == 1
    assert paid["collected_in_window"] == 7000
    assert paid["unpaid_invoices"] == 0
    assert paid["outlets_by_plan"]["growth"] == 1
    assert paid["outlets_by_status"]["active"] == 1


@pytest.mark.asyncio
async def test_plan_and_status_are_validated(client):
    admin = await _auth(client, "admin", "admin123")
    merchant = await _auth(client, "demo", "demo123")
    venue_id = await _my_venue_id(client, merchant)

    bad_plan = await client.put(
        f"/api/admin/venues/{venue_id}/subscription", json={"plan": "platinum", "amount": 1}, headers=admin
    )
    assert bad_plan.status_code == 422
    bad_status = await client.put(
        f"/api/admin/venues/{venue_id}/subscription",
        json={"plan": "growth", "amount": 1, "status": "vibing"},
        headers=admin,
    )
    assert bad_status.status_code == 422
    missing = await client.put(
        "/api/admin/venues/999999/subscription", json={"plan": "growth", "amount": 1}, headers=admin
    )
    assert missing.status_code == 404
    # Recording a payment for a venue with no plan is a conflict, not a crash.
    assert (
        await client.post("/api/admin/venues/%d/subscription/payments" % venue_id, json={}, headers=admin)
    ).status_code == 409
