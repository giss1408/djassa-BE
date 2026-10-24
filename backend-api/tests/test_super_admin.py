"""The super admin, set from Render so Fidelia Admin is never locked out."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.services import super_admin
from tests.helpers import OTHER_PASSWORD, TEST_PASSWORD, make_user, sign_in

PHONE = "0700000010"


@pytest_asyncio.fixture
async def client(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setenv("FIDELIA_SUPER_ADMIN_PHONE", PHONE)
    monkeypatch.setenv("FIDELIA_SUPER_ADMIN_PASSWORD", TEST_PASSWORD)
    limiter.enabled = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


async def _test_accounts(client, password):
    token = (await sign_in(client, PHONE, "admin", password=password)).json()["access_token"]
    return await client.get("/api/admin/accounts/test-accounts", headers={"Authorization": f"Bearer {token}"})


@pytest.mark.asyncio
async def test_the_super_admin_signs_in_to_fidelia_admin_with_super_powers(client):
    await super_admin.ensure_super_admin()
    response = await sign_in(client, PHONE, "admin")
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"
    assert (await _test_accounts(client, TEST_PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_a_new_secret_replaces_a_forgotten_password(client, monkeypatch):
    await super_admin.ensure_super_admin()
    monkeypatch.setenv("FIDELIA_SUPER_ADMIN_PASSWORD", OTHER_PASSWORD)
    await super_admin.ensure_super_admin()
    assert (await sign_in(client, PHONE, "admin")).status_code == 401
    assert (await sign_in(client, PHONE, "admin", password=OTHER_PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_an_existing_number_keeps_its_roles_and_is_unlocked(client):
    await make_user(PHONE, roles="customer", password=None, verified=False)
    await super_admin.ensure_super_admin()
    assert (await sign_in(client, PHONE, "customer")).status_code == 200
    assert (await sign_in(client, PHONE, "admin")).status_code == 200


def test_half_a_setup_stops_the_start(monkeypatch):
    monkeypatch.setenv("FIDELIA_SUPER_ADMIN_PHONE", PHONE)
    monkeypatch.delenv("FIDELIA_SUPER_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        super_admin.super_admin_phone()
