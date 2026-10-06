"""Layaway: paying for one named good in installments.

These hold the guardrails that keep it ordinary commerce: off unless an admin
switches it on for the shop, terms accepted before anything is recorded, a
fixed price and an end date within limits, never more paid than the price, the
good counted as one sale only on handover, and each side seeing only its own
plans.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api.layaway import TERMS_VERSION
from app.core.security import create_access_token
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data

PHONE = "07 12 34 56 78"
CUSTOMER_KEY = "tel:+2250712345678"


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _bearer(sub, role):
    return {"Authorization": f"Bearer {create_access_token({'sub': sub, 'role': role})}"}


async def _merchant(ac):
    r = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _venue():
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()


async def _enable(ac, enabled=True):
    venue = await _venue()
    r = await ac.put(
        f"/api/admin/venues/{venue.id}/layaway", json={"enabled": enabled}, headers=_bearer("tel:+2250700000009", "admin")
    )
    assert r.status_code == 200
    return venue


def _due(days=60):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _plan(**over):
    body = {
        "customer_phone": PHONE,
        "item": "Refrigerateur 90 L",
        "price": 90000,
        "due_by": _due(),
        "terms_version": TERMS_VERSION,
        "terms_accepted": True,
        "first_installment": {"amount": 30000, "idempotency_key": "lay-first-0001"},
    }
    body.update(over)
    return body


async def _open(ac, merchant, **over):
    r = await ac.post("/api/merchant/layaway", json=_plan(**over), headers=merchant)
    assert r.status_code == 201, r.text
    return r.json()


# --- Switched on per shop --------------------------------------------------------


@pytest.mark.asyncio
async def test_layaway_is_off_until_an_admin_switches_it_on_for_the_shop(client):
    merchant = await _merchant(client)
    assert (await client.get("/api/merchant/layaway/settings", headers=merchant)).json()["enabled"] is False
    r = await client.post("/api/merchant/layaway", json=_plan(), headers=merchant)
    assert r.status_code == 403

    await _enable(client)
    settings = (await client.get("/api/merchant/layaway/settings", headers=merchant)).json()
    assert settings["enabled"] is True
    assert settings["terms_version"] == TERMS_VERSION
    assert "pas a Djassa" in settings["terms"]


@pytest.mark.asyncio
async def test_only_an_admin_can_switch_it_on(client):
    merchant = await _merchant(client)
    venue = await _venue()
    r = await client.put(f"/api/admin/venues/{venue.id}/layaway", json={"enabled": True}, headers=merchant)
    assert r.status_code == 403


# --- Opening a plan -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_plan_opens_with_its_first_installment(client):
    merchant = await _merchant(client)
    await _enable(client)
    plan = await _open(client, merchant)
    assert plan["status"] == "open"
    assert (plan["price"], plan["paid"], plan["remaining"]) == (90000, 30000, 60000)
    assert plan["customer"] == "07 •• •• 56 78"
    assert plan["installments"][0]["source"] == "cash_declared"


@pytest.mark.asyncio
async def test_nothing_is_recorded_without_the_customers_agreement_to_the_terms(client):
    merchant = await _merchant(client)
    await _enable(client)
    r = await client.post("/api/merchant/layaway", json=_plan(terms_accepted=False), headers=merchant)
    assert r.status_code == 422
    r = await client.post("/api/merchant/layaway", json=_plan(terms_version="old"), headers=merchant)
    assert r.status_code == 409
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.LayawayPlan))).scalars().all() == []


@pytest.mark.asyncio
async def test_price_and_duration_are_capped(client, monkeypatch):
    monkeypatch.setenv("LAYAWAY_MAX_PRICE", "50000")
    monkeypatch.setenv("LAYAWAY_MAX_DAYS", "90")
    merchant = await _merchant(client)
    await _enable(client)
    assert (await client.post("/api/merchant/layaway", json=_plan(price=60000), headers=merchant)).status_code == 422
    assert (
        await client.post("/api/merchant/layaway", json=_plan(price=40000, due_by=_due(120)), headers=merchant)
    ).status_code == 422
    assert (
        await client.post("/api/merchant/layaway", json=_plan(price=40000, due_by=_due(-1)), headers=merchant)
    ).status_code == 422
    assert (
        await client.post("/api/merchant/layaway", json=_plan(price=40000, due_by=_due(80)), headers=merchant)
    ).status_code == 201


@pytest.mark.asyncio
async def test_a_retried_open_returns_the_same_plan_instead_of_a_second_one(client):
    merchant = await _merchant(client)
    await _enable(client)
    first = await _open(client, merchant)
    again = await client.post("/api/merchant/layaway", json=_plan(), headers=merchant)
    assert again.status_code == 201
    assert again.json()["id"] == first["id"]
    async with AsyncSessionLocal() as db:
        assert len((await db.execute(select(models.LayawayPlan))).scalars().all()) == 1


# --- Installments ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_installments_add_up_and_the_last_one_completes_the_plan(client):
    merchant = await _merchant(client)
    await _enable(client)
    plan = await _open(client, merchant)
    url = f"/api/merchant/layaway/{plan['id']}/installments"
    r = await client.post(url, json={"amount": 30000, "idempotency_key": "lay-inst-0002"}, headers=merchant)
    assert r.json()["status"] == "open"
    r = await client.post(url, json={"amount": 30000, "idempotency_key": "lay-inst-0003"}, headers=merchant)
    body = r.json()
    assert (body["status"], body["paid"], body["remaining"]) == ("completed", 90000, 0)
    assert body["completed_at"] is not None


@pytest.mark.asyncio
async def test_never_more_than_the_price_is_taken(client):
    merchant = await _merchant(client)
    await _enable(client)
    plan = await _open(client, merchant)
    r = await client.post(
        f"/api/merchant/layaway/{plan['id']}/installments",
        json={"amount": 60001, "idempotency_key": "lay-inst-over"},
        headers=merchant,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_a_retried_installment_is_counted_once(client):
    merchant = await _merchant(client)
    await _enable(client)
    plan = await _open(client, merchant)
    url = f"/api/merchant/layaway/{plan['id']}/installments"
    body = {"amount": 10000, "idempotency_key": "lay-inst-retry"}
    assert (await client.post(url, json=body, headers=merchant)).json()["paid"] == 40000
    assert (await client.post(url, json=body, headers=merchant)).json()["paid"] == 40000
    conflict = await client.post(url, json={**body, "amount": 5000}, headers=merchant)
    assert conflict.status_code == 409


# --- Handover and cancelling ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_good_is_handed_over_only_when_paid_and_becomes_one_sale(client):
    merchant = await _merchant(client)
    await _enable(client)
    plan = await _open(client, merchant, first_installment={"amount": 90000, "idempotency_key": "lay-full-0001"})
    assert plan["status"] == "completed"

    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.SaleEvent).where(models.SaleEvent.type == "layaway"))).first() is None

    r = await client.post(f"/api/merchant/layaway/{plan['id']}/deliver", headers=merchant)
    assert r.status_code == 200
    assert r.json()["status"] == "delivered"
    # Delivering twice is harmless and does not create a second sale.
    assert (await client.post(f"/api/merchant/layaway/{plan['id']}/deliver", headers=merchant)).status_code == 200

    async with AsyncSessionLocal() as db:
        sales = (await db.execute(select(models.SaleEvent).where(models.SaleEvent.type == "layaway"))).scalars().all()
    assert len(sales) == 1
    assert (sales[0].amount, sales[0].source, sales[0].customer_id) == (90000, "cash_declared", None)


@pytest.mark.asyncio
async def test_an_unpaid_plan_cannot_be_handed_over(client):
    merchant = await _merchant(client)
    await _enable(client)
    plan = await _open(client, merchant)
    r = await client.post(f"/api/merchant/layaway/{plan['id']}/deliver", headers=merchant)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_cancelling_records_the_refund_and_never_more_than_was_paid(client):
    merchant = await _merchant(client)
    await _enable(client)
    plan = await _open(client, merchant)
    url = f"/api/merchant/layaway/{plan['id']}/cancel"
    assert (await client.post(url, json={"reason": "client parti", "refunded_amount": 30001}, headers=merchant)).status_code == 422
    r = await client.post(url, json={"reason": "client parti", "refunded_amount": 30000}, headers=merchant)
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["refunded_amount"]) == ("cancelled", 30000)
    more = await client.post(
        f"/api/merchant/layaway/{plan['id']}/installments",
        json={"amount": 1000, "idempotency_key": "lay-after-cancel"},
        headers=merchant,
    )
    assert more.status_code == 409


@pytest.mark.asyncio
async def test_a_cashier_cannot_cancel(client):
    r = await client.post(
        "/api/merchant/layaway/1/cancel",
        json={"reason": "x" * 5, "refunded_amount": 0},
        headers=_bearer("tel:+2250700000005", "cashier"),
    )
    assert r.status_code == 403


# --- Who sees what ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_customer_sees_their_plans_and_nobody_elses(client):
    merchant = await _merchant(client)
    await _enable(client)
    await _open(client, merchant)
    await _open(client, merchant, customer_phone="07 99 99 99 99", first_installment=None)

    mine = (await client.get("/api/customer/layaway", headers=_bearer(CUSTOMER_KEY, "customer"))).json()
    assert [p["item"] for p in mine] == ["Refrigerateur 90 L"]
    assert mine[0]["venue_name"]
    other = (await client.get("/api/customer/layaway", headers=_bearer("tel:+2250101010101", "customer"))).json()
    assert other == []


@pytest.mark.asyncio
async def test_another_shops_plan_is_not_found(client):
    merchant = await _merchant(client)
    venue = await _enable(client)
    plan = await _open(client, merchant)
    async with AsyncSessionLocal() as db:
        db_plan = await db.get(models.LayawayPlan, plan["id"])
        other = models.Venue(category="restaurant", name="Autre", commune="Cocody")
        db.add(other)
        await db.flush()
        db_plan.venue_id = other.id
        await db.commit()
    assert venue.id != other.id
    assert (await client.get(f"/api/merchant/layaway/{plan['id']}", headers=merchant)).status_code == 404


# --- The test's own KPIs -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_admin_summary_counts_what_the_test_is_judged_on(client):
    merchant = await _merchant(client)
    await _enable(client)
    done = await _open(client, merchant, first_installment={"amount": 90000, "idempotency_key": "lay-sum-0001"})
    await client.post(f"/api/merchant/layaway/{done['id']}/deliver", headers=merchant)
    dropped = await _open(client, merchant, first_installment={"amount": 1000, "idempotency_key": "lay-sum-0002"})
    await client.post(
        f"/api/merchant/layaway/{dropped['id']}/cancel", json={"reason": "abandon", "refunded_amount": 1000}, headers=merchant
    )
    await _open(client, merchant, first_installment={"amount": 5000, "idempotency_key": "lay-sum-0003"})

    s = (await client.get("/api/admin/layaway", headers=_bearer("tel:+2250700000009", "admin"))).json()
    assert s["venues_enabled"] == 1
    assert s["plans_started"] == 3
    assert s["by_status"] == {"delivered": 1, "cancelled": 1, "open": 1}
    assert s["completion_rate"] == 0.5
    assert s["value_paid"] == 96000
    assert s["customers"] == 1
