"""Logins the team or a shop owner creates wait for a temporary password
the team sends on WhatsApp."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.core.passwords import verify_password
from app.core.phone import normalize_phone
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from tests.helpers import arm, make_user, send_open_check, sign_in

OWNER = "07 00 00 00 02"  # seeded: runs "Chez Tantie Awa (exemple)"
PERSON = "07 31 41 59 26"


@pytest_asyncio.fixture
async def client():
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


async def _admin(ac):
    r = await ac.post("/api/token", data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _state(phone):
    e164 = normalize_phone(phone, "CI")
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one()
        checks = (
            await db.execute(
                select(models.AccountCheck).where(
                    models.AccountCheck.user_id == user.id, models.AccountCheck.status.in_(("pending", "sent"))
                )
            )
        ).scalars().all()
        return user, checks


@pytest.mark.asyncio
async def test_new_merchant_login_waits_in_the_team_queue(client):
    r = await client.post("/api/admin/users/roles", json={"phone": PERSON, "role": "merchant"}, headers=await _admin(client))
    assert r.status_code == 200, r.text
    user, checks = await _state(PERSON)
    assert user.password_hash is None and user.must_change_password is True
    assert [(c.kind, c.status, c.team_created) for c in checks] == [("reset_password", "pending", True)]

    # The team sends the temporary password; it opens a session that must change it.
    temp = await send_open_check(PERSON, "reset_password")
    r = await sign_in(client, PERSON, "merchant", password=temp)
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True and r.json()["verified"] is True


@pytest.mark.asyncio
async def test_merchant_linked_to_a_shop_waits_in_the_team_queue(client):
    shop = {"category": "maquis", "name": "Maquis Nouveau", "commune": "Abobo", "merchant_phone": PERSON}
    r = await client.post("/api/admin/venues", json=shop, headers=await _admin(client))
    assert r.status_code == 201, r.text
    user, checks = await _state(PERSON)
    assert user.password_hash is None and user.must_change_password is True
    assert [(c.kind, c.team_created) for c in checks] == [("reset_password", True)]


@pytest.mark.asyncio
async def test_new_cashier_login_waits_in_the_team_queue(client):
    await arm(OWNER)
    owner = await sign_in(client, OWNER, "merchant")
    h = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    r = await client.post("/api/merchant/staff", json={"phone": PERSON, "name": "Koffi"}, headers=h)
    assert r.status_code == 201, r.text
    user, checks = await _state(PERSON)
    assert user.password_hash is None and user.must_change_password is True
    assert [(c.kind, c.team_created) for c in checks] == [("reset_password", True)]

    temp = await send_open_check(PERSON, "reset_password")
    r = await sign_in(client, PERSON, "merchant", password=temp)
    assert r.status_code == 200 and r.json()["role"] == "cashier"


@pytest.mark.asyncio
async def test_existing_customer_made_merchant_keeps_their_password(client):
    await make_user(PERSON, password="motdepasse1")
    r = await client.post("/api/admin/users/roles", json={"phone": PERSON, "role": "merchant"}, headers=await _admin(client))
    assert r.status_code == 200, r.text
    user, checks = await _state(PERSON)
    assert verify_password("motdepasse1", user.password_hash)
    assert user.must_change_password is False and checks == []
    r = await sign_in(client, PERSON, "merchant")
    assert r.status_code == 200 and r.json()["must_change_password"] is False


@pytest.mark.asyncio
async def test_existing_login_without_a_password_joins_the_queue_once(client):
    await make_user(PERSON, password=None)
    admin = await _admin(client)
    for role in ("merchant", "agent"):
        assert (await client.post("/api/admin/users/roles", json={"phone": PERSON, "role": role}, headers=admin)).status_code == 200
    user, checks = await _state(PERSON)
    assert user.must_change_password is True
    assert [c.kind for c in checks] == ["reset_password"]
