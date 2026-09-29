"""The featured slot as something sold: dated, scarce, expiring, invoiceable."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data


@pytest_asyncio.fixture
async def client():
    # A clean database per test, not just clean tables: slot inventory is finite
    # per commune+category on purpose, so venues and placements left behind by an
    # earlier test would (correctly) report the segment sold out in the next one.
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


def _in(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def _a_deal(ac, merchant, days=5):
    r = await ac.post(
        "/api/merchant/deals",
        json={"title": "Menu du jour", "discount_percent": 20, "ends_at": _in(days)},
        headers=merchant,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_placement_outside_its_window_is_not_in_the_carousel(client):
    """The point of the whole table: a finished campaign stops being sponsored."""
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    customer = await _auth(client, "client", "client123")
    deal = await _a_deal(client, merchant)

    r = await client.post(
        f"/api/admin/deals/{deal['id']}/placements", json={"ends_at": _in(2), "price": 7000}, headers=admin
    )
    assert r.status_code == 201, r.text
    placement_id = r.json()["id"]
    featured = (await client.get("/api/deals", params={"featured": "true"}, headers=customer)).json()
    assert any(d["id"] == deal["id"] for d in featured)

    # Wind the window back into the past, as the clock would.
    async with AsyncSessionLocal() as db:
        p = await db.get(models.DealPlacement, placement_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        p.starts_at, p.ends_at = now - timedelta(days=2), now - timedelta(minutes=1)
        await db.commit()

    # Reads are defended even before the sweep runs.
    featured = (await client.get("/api/deals", params={"featured": "true"}, headers=customer)).json()
    assert all(d["id"] != deal["id"] for d in featured)
    organic = (await client.get("/api/deals", params={"featured": "false"}, headers=customer)).json()
    assert any(d["id"] == deal["id"] for d in organic), "the deal itself is still live, just not sponsored"


@pytest.mark.asyncio
async def test_the_sweep_expires_the_placement_and_clears_the_flag(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    deal = await _a_deal(client, merchant)
    r = await client.post(
        f"/api/admin/deals/{deal['id']}/placements", json={"ends_at": _in(1), "price": 3000}, headers=admin
    )
    placement_id = r.json()["id"]

    async with AsyncSessionLocal() as db:
        p = await db.get(models.DealPlacement, placement_id)
        p.ends_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        await db.commit()

    from app.services.placements import expire_finished_placements

    assert await expire_finished_placements() >= 1
    async with AsyncSessionLocal() as db:
        assert (await db.get(models.DealPlacement, placement_id)).status == "expired"
        assert (await db.get(models.Deal, deal["id"])).is_featured is False


@pytest.mark.asyncio
async def test_only_an_admin_sells_a_slot(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    deal = await _a_deal(client, merchant)
    slot = {"ends_at": _in(1), "price": 5000}

    assert (await client.post(f"/api/admin/deals/{deal['id']}/placements", json=slot, headers=merchant)).status_code == 403
    assert (await client.post(f"/api/admin/deals/{deal['id']}/placements", json=slot, headers=customer)).status_code == 403
    assert (await client.get("/api/admin/placements", headers=merchant)).status_code == 403


@pytest.mark.asyncio
async def test_slot_inventory_is_finite_per_segment(client):
    """Scarcity is the product: overselling a window devalues what is already sold."""
    admin = await _auth(client, "admin", "admin123")

    # Three rivals in a commune of their own, so the count under test is only
    # theirs: the sample data already sells a slot in Cocody, and the point here
    # is the limit itself, not where the sample happens to sit.
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        deals = []
        for i in range(3):
            venue = models.Venue(
                category="maquis",
                name=f"Rival {i} (test)",
                commune="Testville",
                points_per_100=1,
                is_sample=True,
            )
            db.add(venue)
            await db.flush()
            deal = models.Deal(
                venue_id=venue.id,
                title="Concurrent",
                discount_percent=10,
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(days=5),
                is_featured=False,
                active=True,
                created_at=now,
            )
            db.add(deal)
            await db.flush()
            deals.append(deal.id)
        await db.commit()

    slot = {"ends_at": _in(2), "price": 5000}
    for deal_id in deals[:2]:
        r = await client.post(f"/api/admin/deals/{deal_id}/placements", json=slot, headers=admin)
        assert r.status_code == 201, r.text

    # Third overlapping sale in the same segment: sold out.
    third = await client.post(f"/api/admin/deals/{deals[2]}/placements", json=slot, headers=admin)
    assert third.status_code == 409, third.text

    # A window starting after the others have finished is sellable again.
    later = await client.post(
        f"/api/admin/deals/{deals[2]}/placements",
        json={"starts_at": _in(2.5), "ends_at": _in(4), "price": 5000},
        headers=admin,
    )
    assert later.status_code == 201, later.text

    # A different segment is unaffected by Testville being sold out.
    other = (await client.get("/api/admin/placements", headers=admin)).json()
    assert len([p for p in other if p["venue_name"].startswith("Rival")]) == 3


@pytest.mark.asyncio
async def test_a_slot_cannot_outlast_the_deal_it_promotes(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    deal = await _a_deal(client, merchant, days=2)

    # Billing for days the carousel could never show it.
    r = await client.post(
        f"/api/admin/deals/{deal['id']}/placements", json={"ends_at": _in(9), "price": 5000}, headers=admin
    )
    assert r.status_code == 422
    # Already over.
    r = await client.post(
        f"/api/admin/deals/{deal['id']}/placements", json={"ends_at": _in(-1), "price": 5000}, headers=admin
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_what_is_owed_is_listable_and_settlement_is_recorded_once(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    deal = await _a_deal(client, merchant)
    r = await client.post(
        f"/api/admin/deals/{deal['id']}/placements", json={"ends_at": _in(3), "price": 12000}, headers=admin
    )
    placement_id = r.json()["id"]
    assert r.json()["paid_at"] is None

    unpaid = (await client.get("/api/admin/placements", params={"unpaid": "true"}, headers=admin)).json()
    assert any(p["id"] == placement_id and p["price"] == 12000 for p in unpaid)

    paid = await client.post(
        f"/api/admin/placements/{placement_id}/paid", json={"payment_reference": "WAVE-123"}, headers=admin
    )
    assert paid.status_code == 200 and paid.json()["paid_at"] is not None
    first_paid_at = paid.json()["paid_at"]

    # Recording again keeps the original settlement.
    again = await client.post(
        f"/api/admin/placements/{placement_id}/paid", json={"payment_reference": "WAVE-OTHER"}, headers=admin
    )
    assert again.json()["paid_at"] == first_paid_at
    assert again.json()["payment_reference"] == "WAVE-123"

    still_unpaid = (await client.get("/api/admin/placements", params={"unpaid": "true"}, headers=admin)).json()
    assert all(p["id"] != placement_id for p in still_unpaid)


@pytest.mark.asyncio
async def test_cancelling_pulls_the_campaign_but_keeps_the_record(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    customer = await _auth(client, "client", "client123")
    deal = await _a_deal(client, merchant)
    r = await client.post(
        f"/api/admin/deals/{deal['id']}/placements", json={"ends_at": _in(3), "price": 9000}, headers=admin
    )
    placement_id = r.json()["id"]

    cancelled = await client.post(f"/api/admin/placements/{placement_id}/cancel", headers=admin)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled" and cancelled.json()["is_live"] is False

    featured = (await client.get("/api/deals", params={"featured": "true"}, headers=customer)).json()
    assert all(d["id"] != deal["id"] for d in featured)
    # The row survives for the books.
    listed = (await client.get("/api/admin/placements", params={"status": "cancelled"}, headers=admin)).json()
    assert any(p["id"] == placement_id for p in listed)
