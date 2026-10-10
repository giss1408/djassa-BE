"""Push alerts on publish, and offers used at the counter."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data
from app.services import push


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    await _fresh_demo_shop()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _fresh_demo_shop():
    """The suite shares one database: end the demo shop's earlier deals and
    age their alerts, so each test starts below the deal limit and outside the
    one-alert-a-day window."""
    async with AsyncSessionLocal() as db:
        venue_id = (await db.execute(select(models.Venue.id).where(models.Venue.owner_username == "demo"))).scalar_one()
        await db.execute(
            update(models.Deal)
            .where(models.Deal.venue_id == venue_id)
            .values(active=False, notified_at=datetime.utcnow() - timedelta(days=2))
        )
        await db.commit()


class Recorder:
    def __init__(self, fail: bool = False):
        self.sent: list[dict] = []
        self.fail = fail

    async def send(self, message: dict) -> None:
        if self.fail:
            raise push.PushFailed("FCM answered 503")
        self.sent.append(message)


@pytest.fixture
def sender(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(push, "get_sender", lambda: recorder)
    return recorder


async def _auth(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _demo_venue(real: bool) -> models.Venue:
    """The demo merchant's shop, as a real (non-sample) venue when asked:
    sample shops are never announced."""
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))).scalar_one()
        venue.is_sample = not real
        await db.commit()
        return venue


def _in(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def _publish(ac, headers, title="Brochettes a 500 F", **extra):
    body = {"title": title, "price": 500, "original_price": 800, "ends_at": _in(2), **extra}
    r = await ac.post("/api/merchant/deals", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _alert_status(ac, headers, deal_id):
    mine = (await ac.get("/api/merchant/deals", headers=headers)).json()
    return next(d["alert_status"] for d in mine if d["id"] == deal_id)


def test_topic_slug_matches_the_app():
    assert push.topic_slug("Cocody") == "cocody"
    assert push.topic_slug("Port-Bouët") == "port_bouet"
    assert push.topic_slug("  Yopougon  ") == "yopougon"
    assert push.commune_topic("Treichville") == "offers_treichville"


@pytest.mark.asyncio
async def test_publishing_announces_the_deal_to_the_commune_and_the_shop(client, sender):
    venue = await _demo_venue(real=True)
    merchant = await _auth(client, "demo", "demo123")

    deal = await _publish(client, merchant)

    assert len(sender.sent) == 1
    message = sender.sent[0]
    assert message["condition"] == (
        f"'offers_{push.topic_slug(venue.commune)}' in topics || 'venue_{venue.id}' in topics"
    )
    assert message["notification"]["title"] == f"Bon plan · {venue.name}"
    assert "Brochettes a 500 F" in message["notification"]["body"]
    assert "au lieu de" in message["notification"]["body"]
    assert message["data"] == {"type": "deal", "deal_id": str(deal["id"]), "venue_id": str(venue.id)}
    assert await _alert_status(client, merchant, deal["id"]) == "sent"


@pytest.mark.asyncio
async def test_one_alert_per_shop_per_day(client, sender):
    await _demo_venue(real=True)
    merchant = await _auth(client, "demo", "demo123")

    first = await _publish(client, merchant, title="Premier bon plan")
    second = await _publish(client, merchant, title="Deuxieme bon plan")

    assert len(sender.sent) == 1, "the second deal is published but not announced"
    assert await _alert_status(client, merchant, first["id"]) == "sent"
    assert await _alert_status(client, merchant, second["id"]) == "skipped_recent"

    # A day later the shop may announce again.
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(models.Deal)
            .where(models.Deal.id == first["id"])
            .values(notified_at=datetime.utcnow() - timedelta(hours=25))
        )
        await db.commit()
    third = await _publish(client, merchant, title="Troisieme bon plan")
    assert len(sender.sent) == 2
    assert await _alert_status(client, merchant, third["id"]) == "sent"


@pytest.mark.asyncio
async def test_sample_shops_and_later_deals_are_not_announced(client, sender):
    await _demo_venue(real=False)
    merchant = await _auth(client, "demo", "demo123")
    sample = await _publish(client, merchant)
    assert await _alert_status(client, merchant, sample["id"]) == "skipped_sample"

    await _demo_venue(real=True)
    later = await _publish(client, merchant, title="Pour samedi", starts_at=_in(1), ends_at=_in(3))
    assert await _alert_status(client, merchant, later["id"]) == "skipped_future"
    assert sender.sent == []


@pytest.mark.asyncio
async def test_a_failed_alert_never_fails_the_publication(client, monkeypatch):
    monkeypatch.setattr(push, "get_sender", lambda: Recorder(fail=True))
    await _demo_venue(real=True)
    merchant = await _auth(client, "demo", "demo123")

    deal = await _publish(client, merchant)  # still 201

    assert await _alert_status(client, merchant, deal["id"]) == "failed"
    customer = await _auth(client, "client", "client123")
    feed = (await client.get("/api/deals", headers=customer)).json()
    assert any(d["id"] == deal["id"] for d in feed), "the deal is live for customers"


@pytest.mark.asyncio
async def test_merchant_records_customers_who_came_with_a_deal(client, sender):
    merchant = await _auth(client, "demo", "demo123")
    deal = await _publish(client, merchant)

    r = await client.post(
        f"/api/merchant/deals/{deal['id']}/uses", json={"idempotency_key": "tap-0001", "new_customer": True}, headers=merchant
    )
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["new_customer"] is True

    # The same tap retried after a dropped connection: one use, not two.
    again = await client.post(
        f"/api/merchant/deals/{deal['id']}/uses", json={"idempotency_key": "tap-0001", "new_customer": True}, headers=merchant
    )
    assert again.json()["id"] == first["id"]

    # The same key with a different answer is refused, not silently merged.
    clash = await client.post(
        f"/api/merchant/deals/{deal['id']}/uses", json={"idempotency_key": "tap-0001", "new_customer": False}, headers=merchant
    )
    assert clash.status_code == 409

    await client.post(
        f"/api/merchant/deals/{deal['id']}/uses", json={"idempotency_key": "tap-0002", "new_customer": False}, headers=merchant
    )

    summary = (await client.get("/api/merchant/deals/uses/summary", headers=merchant)).json()
    assert summary["days"] == 7
    assert summary["uses"] == 2
    assert summary["new_customers"] == 1
    assert summary["by_deal"] == [{"deal_id": deal["id"], "title": deal["title"], "uses": 2, "new_customers": 1}]


@pytest.mark.asyncio
async def test_only_live_deals_of_the_merchants_own_shop(client, sender):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    deal = await _publish(client, merchant)

    # A customer cannot record uses.
    r = await client.post(
        f"/api/merchant/deals/{deal['id']}/uses", json={"idempotency_key": "tap-cust1", "new_customer": True}, headers=customer
    )
    assert r.status_code == 403

    # Another shop's deal is invisible.
    other = (await client.get("/api/deals", headers=customer)).json()
    foreign = next(d for d in other if d["venue_id"] != deal["venue_id"])
    r = await client.post(
        f"/api/merchant/deals/{foreign['id']}/uses", json={"idempotency_key": "tap-other", "new_customer": True}, headers=merchant
    )
    assert r.status_code == 404

    # An ended deal no longer counts.
    await client.delete(f"/api/merchant/deals/{deal['id']}", headers=merchant)
    r = await client.post(
        f"/api/merchant/deals/{deal['id']}/uses", json={"idempotency_key": "tap-ended", "new_customer": True}, headers=merchant
    )
    assert r.status_code == 409
