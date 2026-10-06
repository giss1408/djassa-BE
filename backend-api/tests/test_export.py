"""Consented export.

This file previously asserted the bug: it granted a consent naming another user,
the caller received it instead, and the export succeeded. The tests below assert
the denial (docs/optimization_claude_hossouko.md, finding 3).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api.export import CUSTOMER_ROWS_SCOPE
from app.db import AsyncSessionLocal, Base, engine
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


async def _a_merchant_row(name="Demo merchant") -> int:
    """A real merchants row. Consent references one, and both databases now
    enforce that reference (tests/conftest.py)."""
    async with AsyncSessionLocal() as db:
        m = models.Merchant(name=name)
        db.add(m)
        await db.commit()
        return m.id


async def _a_paid_sale(ac, merchant, customer, key):
    r = await ac.post("/api/merchant/payment-requests", json={"amount": 3000}, headers=merchant)
    assert r.status_code == 201, r.text
    paid = await ac.post(
        "/api/customer/payments",
        json={
            "pay_code": r.json()["code"],
            "wallet_provider": "wave",
            "payer_msisdn": "+2250700000088",
            "idempotency_key": key,
        },
        headers=customer,
    )
    assert paid.status_code == 201 and paid.json()["status"] == "succeeded", paid.text
    return paid.json()


@pytest.mark.asyncio
async def test_consent_is_recorded_for_the_caller_not_a_third_party(client):
    """The old hole: `user_id` in the body let a caller consent on someone's behalf."""
    customer = await _auth(client, "client", "client123")
    merchant_id = await _a_merchant_row()
    r = await client.post(
        "/api/consents",
        json={"user_id": "someone-else", "merchant_id": merchant_id, "scope": CUSTOMER_ROWS_SCOPE},
        headers=customer,
    )
    assert r.status_code == 201
    assert r.json()["user_id"] == "client", "consent binds the caller, whatever the body claims"

    # An unknown merchant is a 404, not a 500 from the foreign key.
    unknown = await client.post(
        "/api/consents", json={"merchant_id": 999999, "scope": CUSTOMER_ROWS_SCOPE}, headers=customer
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_a_merchant_cannot_export_another_merchants_data(client):
    """There is no merchant id in the path any more, so there is nothing to tamper with."""
    customer = await _auth(client, "client", "client123")
    # A customer is not a merchant: no venue, no export.
    assert (await client.get("/api/export/merchant/revenue.csv", headers=customer)).status_code == 403
    assert (await client.get("/api/export/merchant/customers.csv", headers=customer)).status_code == 403

    # And the old self-granted path is gone entirely.
    assert (await client.get("/api/export/merchant/1", headers=customer)).status_code == 404


@pytest.mark.asyncio
async def test_the_default_export_identifies_no_customer(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await _a_paid_sale(client, merchant, customer, "export-key-1")

    r = await client.get("/api/export/merchant/revenue.csv", headers=merchant)
    assert r.status_code == 200, r.text
    body = r.text
    assert "amount_total" in body and "distinct_customers" in body
    assert "client" not in body, "the aggregate export names no customer"
    assert "customer_id" not in body
    assert "3000" in body


@pytest.mark.asyncio
async def test_customer_rows_are_refused_without_that_customers_consent(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await _a_paid_sale(client, merchant, customer, "export-key-2")

    # Nobody has consented yet.
    refused = await client.get("/api/export/merchant/customers.csv", headers=merchant)
    assert refused.status_code in (403, 409), refused.text

    # Link the venue to a merchant id, then have the customer consent.
    merchant_id = await _a_merchant_row()
    async with AsyncSessionLocal() as db:
        venue = (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()
        venue.merchant_id = merchant_id
        await db.commit()

    still_refused = await client.get("/api/export/merchant/customers.csv", headers=merchant)
    assert still_refused.status_code == 403

    granted = await client.post(
        "/api/consents", json={"merchant_id": merchant_id, "scope": CUSTOMER_ROWS_SCOPE}, headers=customer
    )
    assert granted.status_code == 201

    allowed = await client.get("/api/export/merchant/customers.csv", headers=merchant)
    assert allowed.status_code == 200, allowed.text
    assert "client" in allowed.text


@pytest.mark.asyncio
async def test_the_wrong_scope_does_not_authorize_the_export(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await _a_paid_sale(client, merchant, customer, "export-key-3")

    merchant_id = await _a_merchant_row()
    async with AsyncSessionLocal() as db:
        venue = (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()
        venue.merchant_id = merchant_id
        await db.commit()

    await client.post(
        "/api/consents", json={"merchant_id": merchant_id, "scope": "marketing:email"}, headers=customer
    )
    assert (await client.get("/api/export/merchant/customers.csv", headers=merchant)).status_code == 403


@pytest.mark.asyncio
async def test_every_export_writes_exactly_one_audit_row(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    await _a_paid_sale(client, merchant, customer, "export-key-4")

    assert (await client.get("/api/export/merchant/revenue.csv", headers=merchant)).status_code == 200
    audits = (await client.get("/api/admin/export-audits", headers=admin)).json()
    assert len(audits) == 1
    a = audits[0]
    assert a["exported_by"] == "demo" and a["kind"] == "revenue_summary"
    assert a["subject_count"] == 0, "an aggregate covers no named subject"

    assert (await client.get("/api/export/merchant/revenue.csv", headers=merchant)).status_code == 200
    assert len((await client.get("/api/admin/export-audits", headers=admin)).json()) == 2

    # A merchant cannot read the audit trail.
    assert (await client.get("/api/admin/export-audits", headers=merchant)).status_code == 403


@pytest.mark.asyncio
async def test_a_customer_can_withdraw_their_own_consent_only(client):
    customer = await _auth(client, "client", "client123")
    merchant = await _auth(client, "demo", "demo123")
    merchant_id = await _a_merchant_row()
    r = await client.post(
        "/api/consents", json={"merchant_id": merchant_id, "scope": CUSTOMER_ROWS_SCOPE}, headers=customer
    )
    assert r.status_code == 201, r.text
    consent_id = r.json()["id"]

    # Someone else's consent answers like a missing one.
    assert (await client.delete(f"/api/consents/{consent_id}", headers=merchant)).status_code == 404
    assert (await client.delete(f"/api/consents/{consent_id}", headers=customer)).status_code == 204
    assert (await client.delete(f"/api/consents/{consent_id}", headers=customer)).status_code == 404
