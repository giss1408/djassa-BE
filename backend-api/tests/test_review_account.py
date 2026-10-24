"""The store reviewers' login: one number for Fidelia and Fidelia Pro."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.services import review_account
from tests.helpers import OTHER_PASSWORD, TEST_PASSWORD, make_user, sign_in

PHONE = "0700000077"


@pytest_asyncio.fixture
async def client(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setenv("STORE_REVIEW_PHONE", PHONE)
    monkeypatch.setenv("STORE_REVIEW_PASSWORD", TEST_PASSWORD)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _shops():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.Venue).where(models.Venue.name == review_account.SHOP_NAME))).scalars().all()


@pytest.mark.asyncio
async def test_one_login_opens_both_apps_without_any_whatsapp_code(client):
    await review_account.ensure_review_account()
    for app_name in ("customer", "merchant"):
        response = await sign_in(client, PHONE, app=app_name)
        assert response.status_code == 200, response.text
        assert response.json()["role"] == app_name
    token = (await sign_in(client, PHONE, app="merchant")).json()["access_token"]
    # Fidelia Pro finds the review shop: its deals list answers, empty.
    deals = await client.get("/api/merchant/deals", headers={"Authorization": f"Bearer {token}"})
    assert deals.status_code == 200, deals.text
    assert deals.json() == []


@pytest.mark.asyncio
async def test_every_start_keeps_one_shop_and_takes_a_new_password(client, monkeypatch):
    await review_account.ensure_review_account()
    monkeypatch.setenv("STORE_REVIEW_PASSWORD", OTHER_PASSWORD)
    await review_account.ensure_review_account()
    assert len(await _shops()) == 1
    assert (await sign_in(client, PHONE, password=TEST_PASSWORD)).status_code == 401
    assert (await sign_in(client, PHONE, password=OTHER_PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_an_existing_customer_number_gains_the_shop_and_keeps_its_roles(client):
    await make_user(PHONE, roles="customer,agent", password=None, verified=False)
    await review_account.ensure_review_account()
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == "+225" + PHONE))).scalar_one()
    assert user.role_set() == {"customer", "merchant", "agent"}
    assert user.phone_verified_at is not None


@pytest.mark.asyncio
async def test_the_review_shop_stays_out_of_the_public_catalogue(client):
    await review_account.ensure_review_account()
    names = [v["name"] for v in (await client.get("/api/venues")).json()]
    assert review_account.SHOP_NAME not in names


@pytest.mark.asyncio
async def test_nothing_happens_when_it_is_not_set_up(client, monkeypatch):
    monkeypatch.delenv("STORE_REVIEW_PHONE")
    monkeypatch.delenv("STORE_REVIEW_PASSWORD")
    await review_account.ensure_review_account()
    assert await _shops() == []
    assert review_account.public_venue_filter() == ()


@pytest.mark.parametrize(
    "phone, password",
    [(PHONE, ""), ("", TEST_PASSWORD), (PHONE, "12345678"), (PHONE, "short"), ("not-a-number", TEST_PASSWORD)],
)
def test_half_a_setup_or_a_weak_password_stops_the_start(monkeypatch, phone, password):
    monkeypatch.setenv("STORE_REVIEW_PHONE", phone)
    monkeypatch.setenv("STORE_REVIEW_PASSWORD", password)
    with pytest.raises(RuntimeError):
        review_account.review_phone()
