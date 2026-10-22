"""Register and log in with a phone number and a password."""

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select

from app import models
from app.api.auth import utcnow
from app.core.phone import normalize_phone
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from tests.helpers import make_user, sign_in

PHONE = "0701020304"
E164 = normalize_phone(PHONE, "CI")


@pytest_asyncio.fixture
async def client():
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


async def _user():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()


def _claims(token):
    return jwt.get_unverified_claims(token)


def _register(ac, password="motdepasse1", **extra):
    return ac.post(
        "/api/auth/register",
        json={"phone": PHONE, "country_code": "CI", "password": password, "app": "customer", **extra},
    )


@pytest.mark.asyncio
async def test_register_gives_an_unverified_session(client):
    r = await _register(client, loyalty_consent_version="v1")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verified"] is False and body["must_change_password"] is False
    assert body["role"] == "customer"
    assert _claims(body["access_token"])["vf"] is False
    user = await _user()
    assert user.password_hash and user.phone_verified_at is None
    async with AsyncSessionLocal() as db:
        check = (await db.execute(select(models.AccountCheck).where(models.AccountCheck.user_id == user.id))).scalar_one()
    assert check.kind == "verify_number" and check.consent_version == "v1"


@pytest.mark.asyncio
async def test_register_twice_is_refused(client):
    assert (await _register(client)).status_code == 201
    r = await _register(client)
    assert r.status_code == 409
    assert r.json()["detail"] == "Ce numero a deja un compte. Connectez-vous."


@pytest.mark.asyncio
async def test_existing_account_without_password_must_create_one(client):
    await make_user(PHONE, password=None, verified=True)
    r = await sign_in(client, PHONE)
    assert r.status_code == 409 and r.json() == {"detail": "password_not_set"}
    r = await _register(client)
    assert r.status_code == 201 and r.json()["verified"] is False
    user = await _user()
    assert user.password_hash and user.phone_verified_at is None


@pytest.mark.asyncio
async def test_login_with_right_password(client):
    await make_user(PHONE)
    r = await sign_in(client, PHONE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True and body["must_change_password"] is False
    claims = _claims(body["access_token"])
    assert claims["vf"] is True and claims["pc"] is False


@pytest.mark.asyncio
async def test_unknown_number_and_wrong_password_look_the_same(client):
    await make_user(PHONE)
    wrong = await sign_in(client, PHONE, password="mauvaispass1")
    unknown = await sign_in(client, "0709999999")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Numero ou mot de passe incorrect."}


@pytest.mark.asyncio
async def test_five_wrong_passwords_lock_for_15_minutes(client):
    await make_user(PHONE)
    for _ in range(5):
        assert (await sign_in(client, PHONE, password="mauvaispass1")).status_code == 401
    r = await sign_in(client, PHONE)
    assert r.status_code == 423 and r.json()["detail"] == "Trop d'essais. Reessayez dans 15 minutes."
    user = await _user()
    assert user.failed_logins == 0 and user.locked_until > utcnow() + timedelta(minutes=14)
    async with AsyncSessionLocal() as db:
        u = await db.get(models.User, user.id)
        u.locked_until = utcnow() - timedelta(seconds=1)
        await db.commit()
    assert (await sign_in(client, PHONE)).status_code == 200


@pytest.mark.asyncio
async def test_merchant_app_needs_the_merchant_role(client):
    await make_user(PHONE)
    r = await sign_in(client, PHONE, app="merchant")
    assert r.status_code == 403
    # A wrong password never reveals the missing role.
    assert (await sign_in(client, PHONE, app="merchant", password="mauvaispass1")).status_code == 401
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(models.User))).scalar_one()
        u.roles = "customer,merchant"
        await db.commit()
    r = await sign_in(client, PHONE, app="merchant")
    assert r.status_code == 200 and r.json()["role"] == "merchant"


@pytest.mark.asyncio
async def test_suspended_account_is_refused(client):
    await make_user(PHONE)
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(models.User))).scalar_one()
        u.disabled = True
        await db.commit()
    r = await sign_in(client, PHONE)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_refresh_keeps_the_verified_claim(client):
    await make_user(PHONE, verified=True)
    pair = (await sign_in(client, PHONE)).json()
    r = await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 200
    assert r.json()["verified"] is True and _claims(r.json()["access_token"])["vf"] is True


@pytest.mark.asyncio
async def test_weak_password_is_refused(client):
    r = await _register(client, password="12345678")
    assert r.status_code == 422
    assert r.json()["detail"] == "Le mot de passe ne peut pas etre compose uniquement de chiffres."
    r = await _register(client, password="court")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_correct_password_resets_the_miss_counter(client):
    await make_user(PHONE)
    for _ in range(4):
        assert (await sign_in(client, PHONE, password="mauvaispass1")).status_code == 401
    assert (await sign_in(client, PHONE)).status_code == 200
    for _ in range(4):
        assert (await sign_in(client, PHONE, password="mauvaispass1")).status_code == 401
