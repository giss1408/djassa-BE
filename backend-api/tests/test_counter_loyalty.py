"""Points on cash sales, for customers identified by phone at the counter.

The merchant app has always asked for an optional customer number on a cash
sale; until now it was kept on the phone and never sent, so a cash customer
earned nothing. These cover the loop the concept depends on: recognised by
phone, points earned, balance read and reward handed over at the counter --
without the customer app, and without leaking points across venues or twice.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.core.phone import InvalidPhone, mask_phone, normalize_phone
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


async def _auth(ac, username="demo", password="demo123"):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _venue_of(username="demo"):
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == username))
        ).scalars().first()


async def _sale(ac, merchant, key, amount="2500", phone="07 12 34 56 78", consent=True):
    body = {"amount": amount, "currency": "XOF", "type": "sale", "idempotency_key": key}
    if phone is not None:
        body["customer_phone"] = phone
        body["customer_consent"] = consent
    return await ac.post("/api/merchant/sales", json=body, headers=merchant)


# --- Phone normalisation ------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["07 12 34 56 78", "0712345678", "07.12.34.56.78", "+225 07 12 34 56 78", "00225 0712345678"],
)
def test_every_way_of_typing_one_ivorian_number_gives_one_key(raw):
    assert normalize_phone(raw) == "+2250712345678"


@pytest.mark.parametrize("raw", ["", "12345", "7123456789", "+225712345678", "07 12 34 56 7x", "+33612345678"])
def test_anything_else_is_refused_rather_than_stored_as_a_second_customer(raw):
    with pytest.raises(InvalidPhone):
        normalize_phone(raw)


def test_the_masked_form_is_enough_to_check_the_number_without_repeating_it():
    assert mask_phone("+2250712345678") == "07 •• •• 56 78"


# --- Earning on a cash sale ---------------------------------------------------


@pytest.mark.asyncio
async def test_a_cash_sale_with_a_number_earns_the_venues_points(client):
    merchant = await _auth(client)
    venue = await _venue_of()
    r = await _sale(client, merchant, "cash-pts-0001", amount="2500")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "cash_declared"
    assert body["points_awarded"] == 25 * venue.points_per_100
    assert body["customer"] == "07 •• •• 56 78"
    # The full number is never echoed back.
    assert "0712345678" not in r.text

    async with AsyncSessionLocal() as db:
        entry = (await db.execute(select(models.LoyaltyEntry))).scalars().one()
        event = (await db.execute(select(models.SaleEvent))).scalars().one()
    assert entry.customer_id == "tel:+2250712345678"
    assert entry.reason == "cash_sale"
    assert event.customer_id == "tel:+2250712345678"
    assert event.loyalty_entry_id == entry.id


@pytest.mark.asyncio
async def test_an_anonymous_cash_sale_still_records_and_earns_nothing(client):
    merchant = await _auth(client)
    r = await _sale(client, merchant, "cash-anon-001", phone=None)
    assert r.status_code == 201, r.text
    assert r.json()["points_awarded"] == 0
    assert r.json()["customer"] is None
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.LoyaltyEntry))).scalars().first() is None


@pytest.mark.asyncio
async def test_a_bad_number_is_refused_so_the_promised_points_are_not_silently_lost(client):
    merchant = await _auth(client)
    r = await _sale(client, merchant, "cash-badnum-1", phone="12345")
    assert r.status_code == 422
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.SaleEvent))).scalars().first() is None


@pytest.mark.asyncio
async def test_a_retried_sale_never_pays_points_twice(client):
    merchant = await _auth(client)
    first = await _sale(client, merchant, "cash-retry-01")
    again = await _sale(client, merchant, "cash-retry-01")
    assert first.status_code == again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    # The retry reports the points already granted, and grants none.
    assert again.json()["points_awarded"] == first.json()["points_awarded"]
    async with AsyncSessionLocal() as db:
        assert len((await db.execute(select(models.LoyaltyEntry))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_the_same_key_with_another_customer_is_a_conflict(client):
    merchant = await _auth(client)
    assert (await _sale(client, merchant, "cash-conflict1")).status_code == 201
    other = await _sale(client, merchant, "cash-conflict1", phone="05 00 00 00 01")
    assert other.status_code == 409


@pytest.mark.asyncio
async def test_the_offline_queue_carries_the_number_and_reports_points_per_sale(client):
    merchant = await _auth(client)
    r = await client.post(
        "/api/merchant/sales/sync",
        json={
            "operations": [
                {"amount": "1000", "idempotency_key": "sync-pts-0001", "customer_phone": "0712345678",
                 "customer_consent": True},
                {"amount": "1000", "idempotency_key": "sync-pts-0002"},
                {"amount": "1000", "idempotency_key": "sync-pts-0003", "customer_phone": "nope"},
            ]
        },
        headers=merchant,
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert [x["status"] for x in results] == ["accepted", "accepted", "rejected"]
    assert results[0]["sale"]["points_awarded"] > 0
    assert results[1]["sale"]["points_awarded"] == 0


# --- Balance and reward at the counter ---------------------------------------


@pytest.mark.asyncio
async def test_the_merchant_reads_the_balance_and_hands_over_a_reward(client):
    merchant = await _auth(client)
    venue = await _venue_of()
    for i in range(8):
        assert (await _sale(client, merchant, f"cash-loop-{i:04d}", amount="5000")).status_code == 201

    looked = await client.post("/api/merchant/customers/loyalty", json={"phone": "+225 0712345678"}, headers=merchant)
    assert looked.status_code == 200, looked.text
    balance = looked.json()
    assert balance["customer"] == "07 •• •• 56 78"
    assert balance["points"] == 8 * 50 * venue.points_per_100
    assert balance["rewards"], "the demo venue has rewards"

    reward = min(balance["rewards"], key=lambda x: x["cost_points"])
    given = await client.post(
        "/api/merchant/customers/redeem", json={"phone": "07 12 34 56 78", "reward_id": reward["id"]}, headers=merchant
    )
    assert given.status_code == 201, given.text
    assert len(given.json()["voucher_code"]) == 6
    assert given.json()["remaining_points"] == balance["points"] - reward["cost_points"]

    after = await client.post("/api/merchant/customers/loyalty", json={"phone": "0712345678"}, headers=merchant)
    assert after.json()["points"] == balance["points"] - reward["cost_points"]


@pytest.mark.asyncio
async def test_not_enough_points_is_refused(client):
    merchant = await _auth(client)
    looked = await client.post("/api/merchant/customers/loyalty", json={"phone": "0799999999"}, headers=merchant)
    assert looked.json()["points"] == 0
    reward = looked.json()["rewards"][0]
    r = await client.post(
        "/api/merchant/customers/redeem", json={"phone": "0799999999", "reward_id": reward["id"]}, headers=merchant
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_a_merchant_cannot_spend_points_on_another_venues_reward(client):
    merchant = await _auth(client)
    for i in range(8):
        await _sale(client, merchant, f"cash-xven-{i:04d}", amount="5000")
    venue = await _venue_of()
    async with AsyncSessionLocal() as db:
        foreign = (
            await db.execute(select(models.LoyaltyReward).where(models.LoyaltyReward.venue_id != venue.id))
        ).scalars().first()
    assert foreign is not None
    r = await client.post(
        "/api/merchant/customers/redeem", json={"phone": "0712345678", "reward_id": foreign.id}, headers=merchant
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_phone_points_do_not_leak_into_a_customer_account_that_claims_the_number(client):
    """Tier 0 profiles declare a number without proving it, so claiming one
    must not collect someone else's points."""
    merchant = await _auth(client)
    await _sale(client, merchant, "cash-claim-001", amount="5000")
    customer = await _auth(client, "client", "client123")
    await client.post(
        "/api/identity/profile",
        json={"country_code": "CI", "phone_e164": "+2250712345678", "operator": "wave", "consent_version": "v1"},
        headers=customer,
    )
    mine = await client.get("/api/customer/loyalty", headers=customer)
    assert mine.status_code == 200
    assert mine.json()["total_points"] == 0


@pytest.mark.asyncio
async def test_counter_endpoints_are_for_merchants_only(client):
    customer = await _auth(client, "client", "client123")
    r = await client.post("/api/merchant/customers/loyalty", json={"phone": "0712345678"}, headers=customer)
    assert r.status_code == 403


# --- Consent (docs/Reglementation/ARTCI.md, option 1) -------------------------


@pytest.mark.asyncio
async def test_a_number_without_consent_is_refused_so_the_merchant_can_ask(client):
    merchant = await _auth(client)
    r = await _sale(client, merchant, "consent-0001", consent=False)
    assert r.status_code == 422
    assert "accepte" in r.json()["detail"]
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.SaleEvent).where(models.SaleEvent.idempotency_key == "sale:consent-0001"))).first() is None


@pytest.mark.asyncio
async def test_consent_given_once_at_the_counter_is_on_file_for_the_next_sale(client):
    merchant = await _auth(client)
    assert (await _sale(client, merchant, "consent-0002", consent=True)).status_code == 201
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(models.LoyaltyConsent))).scalar_one()
        assert row.customer_id == "tel:+2250712345678" and row.source == "counter" and row.venue_id is not None
    # Next visit: the number already agreed, no need to tick the box again.
    r = await _sale(client, merchant, "consent-0003", consent=False)
    assert r.status_code == 201 and r.json()["points_awarded"] > 0
