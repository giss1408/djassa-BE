"""One event stream, labelled by evidence class.

The finding these cover: `Transaction` (whatever the retailer app typed, keyed on
a client-supplied `merchant_id`) and `CustomerPayment` (confirmed by the
aggregator) never touched, and the credit export read the unverified one
(docs/optimization_claude_djassa.md, finding 2).
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data
from app.services.sale_events import CONFIRMED, DECLARED


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


async def _pay(ac, merchant, customer, key, amount=3000, msisdn="+2250700000088"):
    """A customer paying the demo venue's QR. Settles instantly (fake provider)."""
    req = await ac.post("/api/merchant/payment-requests", json={"amount": amount}, headers=merchant)
    assert req.status_code == 201, req.text
    paid = await ac.post(
        "/api/customer/payments",
        json={
            "pay_code": req.json()["code"],
            "wallet_provider": "wave",
            "payer_msisdn": msisdn,
            "idempotency_key": key,
        },
        headers=customer,
    )
    assert paid.status_code == 201, paid.text
    return paid.json()


async def _events(**where):
    async with AsyncSessionLocal() as db:
        stmt = select(models.SaleEvent)
        for column, value in where.items():
            stmt = stmt.where(getattr(models.SaleEvent, column) == value)
        return list((await db.execute(stmt.order_by(models.SaleEvent.id))).scalars().all())


@pytest.mark.asyncio
async def test_a_succeeded_payment_writes_exactly_one_confirmed_event(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    paid = await _pay(client, merchant, customer, "ev-confirmed-1", amount=4500)
    assert paid["status"] == "succeeded"

    events = await _events(source=CONFIRMED)
    assert len(events) == 1
    event = events[0]
    assert Decimal(event.amount) == 4500
    assert event.status == "recorded"
    assert event.customer_id == "client"
    assert event.payment_id is not None
    # The link the merged stream exists to create: one row ties the payment, the
    # venue and the points together.
    assert event.venue_id is not None
    assert event.loyalty_entry_id is not None


@pytest.mark.asyncio
async def test_a_failed_payment_writes_no_event(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    # The fake provider declines a payer number ending 0000.
    declined = await _pay(client, merchant, customer, "ev-failed-1", msisdn="+2250700000000")
    assert declined["status"] == "failed"

    assert await _events() == [], "a decline is not a sale"


@pytest.mark.asyncio
async def test_a_declared_sale_cannot_choose_its_own_venue(client):
    merchant = await _auth(client, "demo", "demo123")
    body = {"amount": "2500", "currency": "XOF", "type": "sale", "idempotency_key": "declared-key-1"}

    r = await client.post("/api/merchant/sales", json=body, headers=merchant)
    assert r.status_code == 201, r.text
    assert r.json()["source"] == DECLARED

    async with AsyncSessionLocal() as db:
        demo_venue = (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()
    assert r.json()["venue_id"] == demo_venue.id

    # There is no field to tamper with: an extra venue_id/merchant_id in the
    # body is not part of the schema and changes nothing.
    ignored = await client.post(
        "/api/merchant/sales",
        json={**body, "idempotency_key": "declared-key-2", "venue_id": 9999, "merchant_id": 9999},
        headers=merchant,
    )
    assert ignored.status_code == 201
    assert ignored.json()["venue_id"] == demo_venue.id


@pytest.mark.asyncio
async def test_only_a_merchant_can_declare_a_sale(client):
    customer = await _auth(client, "client", "client123")
    body = {"amount": "1000", "idempotency_key": "declared-forbidden"}
    assert (await client.post("/api/merchant/sales", json=body, headers=customer)).status_code == 403


@pytest.mark.asyncio
async def test_replaying_an_idempotency_key_creates_no_second_event(client):
    merchant = await _auth(client, "demo", "demo123")
    body = {"amount": "1500", "currency": "XOF", "type": "sale", "idempotency_key": "declared-replay"}

    first = await client.post("/api/merchant/sales", json=body, headers=merchant)
    second = await client.post("/api/merchant/sales", json=body, headers=merchant)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(await _events(source=DECLARED)) == 1

    # The same key with a different amount is two different sales sharing a key:
    # answering with the first would quietly lose the second.
    conflict = await client.post("/api/merchant/sales", json={**body, "amount": "9900"}, headers=merchant)
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_the_offline_queue_drains_in_one_request_and_reports_per_row(client):
    merchant = await _auth(client, "demo", "demo123")
    operations = [
        {"amount": "1000", "idempotency_key": "batch-key-a", "type": "sale"},
        {"amount": "2000", "idempotency_key": "batch-key-b", "type": "sale"},
    ]
    first = await client.post("/api/merchant/sales/sync", json={"operations": operations}, headers=merchant)
    assert first.status_code == 200, first.text
    assert [r["status"] for r in first.json()["results"]] == ["accepted", "accepted"]

    # A replayed batch is recognised, not re-recorded -- the guarantee the
    # device's queue depends on when a response is lost.
    replay = await client.post("/api/merchant/sales/sync", json={"operations": operations}, headers=merchant)
    assert [r["status"] for r in replay.json()["results"]] == ["already_processed", "already_processed"]
    assert len(await _events(source=DECLARED)) == 2

    # One bad row does not block the good ones in the same batch.
    mixed = await client.post(
        "/api/merchant/sales/sync",
        json={
            "operations": [
                {"amount": "5000", "idempotency_key": "batch-key-a", "type": "sale"},  # key reuse, new amount
                {"amount": "3000", "idempotency_key": "batch-key-c", "type": "sale"},
            ]
        },
        headers=merchant,
    )
    statuses = [r["status"] for r in mixed.json()["results"]]
    assert statuses == ["rejected", "accepted"], mixed.json()
    assert len(await _events(source=DECLARED)) == 3


@pytest.mark.asyncio
async def test_a_queued_sale_keeps_the_day_it_was_made(client):
    """`occurred_at` is the merchant's day; `recorded_at` is when it reached us.

    Flattening the two would move a sale queued overnight into the wrong day's
    takings, and the gap is itself the offline-window signal.
    """
    merchant = await _auth(client, "demo", "demo123")
    r = await client.post(
        "/api/merchant/sales",
        json={
            "amount": "1200",
            "idempotency_key": "declared-backdated",
            "occurred_at": "2026-09-20T19:30:00",
        },
        headers=merchant,
    )
    assert r.status_code == 201, r.text
    event = (await _events(idempotency_key="sale:declared-backdated"))[0]
    assert event.occurred_at.date().isoformat() == "2026-09-20"
    assert event.recorded_at > event.occurred_at


@pytest.mark.asyncio
async def test_stats_split_confirmed_from_declared_and_reconcile_with_the_stream(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")

    await _pay(client, merchant, customer, "stats-confirmed-1", amount=4000)
    await _pay(client, merchant, customer, "stats-confirmed-2", amount=6000)
    await client.post(
        "/api/merchant/sales",
        json={"amount": "2500", "idempotency_key": "stats-declared-1"},
        headers=merchant,
    )

    stats = (await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)).json()
    # `revenue` keeps its old meaning exactly: money that arrived through Djassa.
    assert stats["revenue"] == 10000
    assert stats["confirmed_revenue"] == 10000
    assert stats["declared_revenue"] == 2500
    assert stats["declared_sales"] == 1
    assert stats["turnover"] == 12500
    # 10000 / 12500
    assert stats["verified_share"] == 0.8

    async with AsyncSessionLocal() as db:
        total = (
            await db.execute(
                select(func.coalesce(func.sum(models.SaleEvent.amount), 0)).where(
                    models.SaleEvent.status == "recorded"
                )
            )
        ).scalar_one()
    assert Decimal(total) == stats["turnover"], "stats must be a SUM over the stream, not a parallel count"


@pytest.mark.asyncio
async def test_verified_share_moves_when_the_payment_mix_changes(client):
    """The merchant's own incentive to push customers to digital payment."""
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")

    await client.post(
        "/api/merchant/sales", json={"amount": "5000", "idempotency_key": "mix-cash-1"}, headers=merchant
    )
    all_cash = (await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)).json()
    assert all_cash["verified_share"] == 0.0

    await _pay(client, merchant, customer, "mix-confirmed-1", amount=5000)
    half = (await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)).json()
    assert half["verified_share"] == 0.5

    await _pay(client, merchant, customer, "mix-confirmed-2", amount=10000)
    mostly = (await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)).json()
    assert mostly["verified_share"] == 0.75
    assert mostly["regularity"] > 0


@pytest.mark.asyncio
async def test_an_empty_stream_reports_zero_verified_share_not_a_perfect_one(client):
    """A venue that sold nothing has verified nothing.

    The friendlier rounding (0/0 = 1.0) would flatter an empty history in the one
    document a lender reads.
    """
    merchant = await _auth(client, "demo", "demo123")
    stats = (await client.get("/api/merchant/stats", params={"days": 7}, headers=merchant)).json()
    assert stats["turnover"] == 0
    assert stats["verified_share"] == 0.0


@pytest.mark.asyncio
async def test_the_revenue_export_reads_the_merged_stream_and_labels_both_halves(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await _pay(client, merchant, customer, "export-merged-1", amount=7000)
    await client.post(
        "/api/merchant/sales", json={"amount": "3000", "idempotency_key": "export-merged-cash"}, headers=merchant
    )

    r = await client.get("/api/export/merchant/revenue.csv", headers=merchant)
    assert r.status_code == 200, r.text
    body = r.text
    assert "amount_confirmed" in body and "amount_declared" in body
    assert "verified_share" in body
    assert "0.7" in body, "7000 confirmed of 10000 total"
    # Still no customer named in the aggregate form.
    assert "client" not in body


@pytest.mark.asyncio
async def test_a_cash_sale_never_appears_in_the_per_customer_export(client):
    """A cash sale has no customer, so no customer can have consented to it."""
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await _pay(client, merchant, customer, "cust-export-confirmed", amount=2000)
    await client.post(
        "/api/merchant/sales", json={"amount": "8888", "idempotency_key": "cust-export-cash"}, headers=merchant
    )

    async with AsyncSessionLocal() as db:
        m = models.Merchant(name="Export merchant")
        db.add(m)
        await db.flush()
        merchant_id = m.id
        venue = (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()
        venue.merchant_id = merchant_id
        await db.commit()

    granted = await client.post(
        "/api/consents", json={"merchant_id": merchant_id, "scope": "transactions:export"}, headers=customer
    )
    assert granted.status_code == 201, granted.text

    r = await client.get("/api/export/merchant/customers.csv", headers=merchant)
    assert r.status_code == 200, r.text
    assert "client" in r.text
    assert "2000" in r.text
    assert "8888" not in r.text, "an anonymous cash sale has no data subject"
    assert "mobile_money_confirmed" in r.text, "every row states its evidence class"
