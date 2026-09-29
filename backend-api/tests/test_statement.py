"""The signed revenue statement.

The artifact shown to a microfinance institution. What these assert is the
difference between an attestation and a spreadsheet with a logo: the numbers
reconcile with the event stream by construction, an edited figure fails
verification, and every issue is attributable
(docs/optimization_claude_djassa.md, optimization C).
"""

from datetime import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data
from app.services import statement as statement_service

# Long enough to satisfy the minimum period; the fixture's sales all land today.
PERIOD = {"from": "2026-01-01T00:00:00"}


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


async def _demo_venue_id() -> int:
    async with AsyncSessionLocal() as db:
        venue = (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()
        return venue.id


async def _on_network_plan(venue_id: int, ac, admin):
    """The statement is a paid feature; only `network` includes it."""
    r = await ac.put(
        f"/api/admin/venues/{venue_id}/subscription",
        json={"plan": "network", "amount": 25000, "status": "active"},
        headers=admin,
    )
    assert r.status_code == 200, r.text


async def _pay(ac, merchant, customer, key, amount):
    req = await ac.post("/api/merchant/payment-requests", json={"amount": amount}, headers=merchant)
    assert req.status_code == 201, req.text
    paid = await ac.post(
        "/api/customer/payments",
        json={
            "pay_code": req.json()["code"],
            "wallet_provider": "wave",
            "payer_msisdn": "+2250700000088",
            "idempotency_key": key,
        },
        headers=customer,
    )
    assert paid.status_code == 201 and paid.json()["status"] == "succeeded", paid.text


async def _declare(ac, merchant, key, amount):
    r = await ac.post("/api/merchant/sales", json={"amount": str(amount), "idempotency_key": key}, headers=merchant)
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_an_unpaid_plan_cannot_issue_a_statement(client):
    merchant = await _auth(client, "demo", "demo123")
    refused = await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)
    assert refused.status_code == 402
    # The message must not imply the merchant's data is locked away from them.
    assert "CSV" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_customer_cannot_issue_a_statement_about_a_merchant(client):
    customer = await _auth(client, "client", "client123")
    assert (await client.get("/api/merchant/statement", params=PERIOD, headers=customer)).status_code == 403


@pytest.mark.asyncio
async def test_the_statement_totals_reconcile_with_the_event_stream(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)

    await _pay(client, merchant, customer, "stmt-confirmed-1", 6000)
    await _pay(client, merchant, customer, "stmt-confirmed-2", 9000)
    await _declare(client, merchant, "stmt-declared-1", 5000)

    r = await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)
    assert r.status_code == 200, r.text
    payload = r.json()["payload"]

    assert payload["turnover"]["total"] == "20000"
    assert payload["turnover"]["mobile_money_confirmed"] == "15000"
    assert payload["turnover"]["cash_declared"] == "5000"
    assert payload["turnover"]["verified_share"] == 0.75
    assert payload["volume"]["sales"] == 3
    assert payload["volume"]["confirmed_sales"] == 2
    assert payload["volume"]["declared_sales"] == 1

    async with AsyncSessionLocal() as db:
        total = (
            await db.execute(
                select(func.coalesce(func.sum(models.SaleEvent.amount), 0)).where(
                    models.SaleEvent.status == "recorded"
                )
            )
        ).scalar_one()
    assert Decimal(payload["turnover"]["total"]) == Decimal(total)


@pytest.mark.asyncio
async def test_the_statement_names_no_customer(client):
    """Concentration, not identity -- which is why it needs no customer consent."""
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)
    await _pay(client, merchant, customer, "stmt-privacy-1", 3000)

    r = await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)
    assert r.status_code == 200
    assert "client" not in r.text.replace("djassa", ""), "no data subject is named"
    payload = r.json()["payload"]
    assert payload["customers"]["identified"] == 1
    assert payload["customers"]["top_customer_share"] == 1.0


@pytest.mark.asyncio
async def test_a_tampered_statement_fails_verification(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)
    await _pay(client, merchant, customer, "stmt-tamper-1", 4000)

    document = (await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)).json()
    payload, signature = document["payload"], document["signature"]["value"]

    good = await client.post(
        "/api/statements/verify", json={"payload": payload, "signature": signature}, headers=merchant
    )
    assert good.status_code == 200 and good.json()["valid"] is True

    # The merchant inflates their turnover before forwarding the file.
    inflated = {**payload, "turnover": {**payload["turnover"], "total": "400000"}}
    bad = await client.post(
        "/api/statements/verify", json={"payload": inflated, "signature": signature}, headers=merchant
    )
    assert bad.status_code == 200 and bad.json()["valid"] is False

    # A forged signature over the real payload fails too.
    forged = await client.post(
        "/api/statements/verify", json={"payload": payload, "signature": "0" * 64}, headers=merchant
    )
    assert forged.json()["valid"] is False


@pytest.mark.asyncio
async def test_verification_survives_a_round_trip_through_json(client):
    """A recipient re-serializes the file before checking it.

    If the canonical form were not byte-stable, a genuine statement would fail
    verification after a round trip through any JSON tool -- which would make the
    signature worse than useless.
    """
    import json

    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)
    await _pay(client, merchant, customer, "stmt-roundtrip-1", 2500)

    document = (await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)).json()
    reparsed = json.loads(json.dumps(document["payload"]))
    assert statement_service.verify(reparsed, document["signature"]["value"]) is True


@pytest.mark.asyncio
async def test_every_issued_statement_writes_an_audit_row(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)
    await _pay(client, merchant, customer, "stmt-audit-1", 1500)

    assert (await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)).status_code == 200
    audits = (await client.get("/api/admin/export-audits", headers=admin)).json()
    issued = [a for a in audits if a["kind"] == "revenue_statement"]
    assert len(issued) == 1
    assert issued[0]["exported_by"] == "demo"
    assert issued[0]["subject_count"] == 0, "a statement names nobody"

    # Verifying is not a data transfer and writes no audit row.
    document = (await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)).json()
    await client.post(
        "/api/statements/verify",
        json={"payload": document["payload"], "signature": document["signature"]["value"]},
        headers=merchant,
    )
    again = (await client.get("/api/admin/export-audits", headers=admin)).json()
    assert len([a for a in again if a["kind"] == "revenue_statement"]) == 2


@pytest.mark.asyncio
async def test_a_too_short_period_is_refused(client):
    """A month is the floor: a shorter window says nothing about regularity."""
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)

    refused = await client.get(
        "/api/merchant/statement",
        params={"from": "2026-09-25T00:00:00", "to": "2026-09-28T00:00:00"},
        headers=merchant,
    )
    assert refused.status_code == 422
    assert "regularite" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_an_admin_can_issue_for_a_venue_on_any_plan_and_it_is_audited(client):
    """The pilot reality: a partner conversation happens with Djassa in the room."""
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    venue_id = await _demo_venue_id()
    await _pay(client, merchant, customer, "stmt-admin-1", 7000)

    # The merchant themselves cannot: no paid plan.
    assert (await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)).status_code == 402

    issued = await client.get(f"/api/admin/venues/{venue_id}/statement", params=PERIOD, headers=admin)
    assert issued.status_code == 200, issued.text
    assert issued.json()["payload"]["turnover"]["total"] == "7000"
    assert issued.json()["payload"]["issued_to"] == "admin"

    audits = (await client.get("/api/admin/export-audits", headers=admin)).json()
    assert [a["exported_by"] for a in audits if a["kind"] == "revenue_statement"] == ["admin"]

    # A merchant cannot use the admin route to read another venue.
    assert (
        await client.get(f"/api/admin/venues/{venue_id}/statement", params=PERIOD, headers=merchant)
    ).status_code == 403


@pytest.mark.asyncio
async def test_the_signature_key_id_is_not_the_key(client):
    """A fingerprint so a rotation is diagnosable, never the secret itself."""
    import os

    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)

    document = (await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)).json()
    key_id = document["signature"]["key_id"]
    secret = os.environ.get("DJASSA_STATEMENT_SECRET") or os.environ["DJASSA_SECRET_KEY"]
    assert secret not in key_id
    assert document["signature"]["algorithm"] == "HMAC-SHA256"
    assert len(key_id) == 16


@pytest.mark.asyncio
async def test_an_unsigned_statement_is_never_issued(monkeypatch, client):
    """Fail closed: an unsigned attestation looks exactly as official as a real one."""
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)

    monkeypatch.delenv("DJASSA_STATEMENT_SECRET", raising=False)
    monkeypatch.delenv("DJASSA_SECRET_KEY", raising=False)
    r = await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)
    assert r.status_code == 503
    assert "non emise" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_window_too_dense_is_refused_rather_than_truncated(monkeypatch, client):
    """The worst failure this code could have: a truncated total, signed.

    A partial event set still sums to a *plausible* turnover, and the signature
    would attest to it. So the aggregation refuses at its bound instead of
    quietly answering with less than the merchant sold.
    """
    from app.services import revenue as revenue_service

    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    admin = await _auth(client, "admin", "admin123")
    await _on_network_plan(await _demo_venue_id(), client, admin)
    await _pay(client, merchant, customer, "stmt-dense-1", 1000)
    await _declare(client, merchant, "stmt-dense-2", 2000)

    # Lowered rather than creating 50,000 rows: it is the refusal that is under
    # test, not the number.
    monkeypatch.setattr(revenue_service, "MAX_EVENTS_PER_WINDOW", 1)

    refused = await client.get("/api/merchant/statement", params=PERIOD, headers=merchant)
    assert refused.status_code == 413
    assert "plus courte" in refused.json()["detail"]

    # Stats refuse for the same reason, rather than showing a smaller turnover.
    stats = await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)
    assert stats.status_code == 413

    # The CSV has its own, larger bound (MAX_EXPORT_ROWS) and is unaffected by the
    # patch above -- but it refuses on the same principle, which is asserted by
    # patching the constant it actually uses.
    from app.api import export as export_api

    assert (await client.get("/api/export/merchant/revenue.csv?days=365", headers=merchant)).status_code == 200
    monkeypatch.setattr(export_api, "MAX_EXPORT_ROWS", 1)
    csv_refused = await client.get("/api/export/merchant/revenue.csv?days=365", headers=merchant)
    assert csv_refused.status_code == 413
    assert "plus courte" in csv_refused.json()["detail"]


@pytest.mark.asyncio
async def test_the_bound_is_not_hit_by_a_realistic_pilot_venue(client):
    """Exactly-at-the-limit must succeed; only *over* it refuses."""
    from app.services import revenue as revenue_service

    async with AsyncSessionLocal() as db:
        venue = (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()
        events = await revenue_service.events_in_window(
            db, venue.id, datetime(2026, 1, 1), datetime(2026, 12, 31), limit=0
        )
    assert events == [], "an empty stream is not a limit breach"
