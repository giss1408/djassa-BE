"""Nobody takes over an account without the code or password sent to its number."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api.auth import issue_tokens, utcnow
from app.core import tokens
from app.core.phone import normalize_phone, phone_key
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from tests.helpers import OTHER_PASSWORD, SQUATTER_PASSWORD, TEST_PASSWORD, WRONG_PASSWORD, make_user, send_open_check, sign_in

PHONE = "0701020304"
E164 = normalize_phone(PHONE, "CI")
CLAIM_ANSWER = {"message": "Fidelia va vous envoyer un code sur WhatsApp. Saisissez-le avec votre mot de passe."}


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


def _auth(pair):
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def _user():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()


async def _old_session(role="customer"):
    """A refresh token the owner got earlier (by SMS, before passwords)."""
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()
        pair = await issue_tokens(db, user, role, tokens.new_family(), utcnow())
        await db.commit()
    return pair.model_dump()


def _register(ac, password=SQUATTER_PASSWORD):
    return ac.post("/api/auth/register", json={"phone": PHONE, "country_code": "CI", "password": password})


def _claim(ac, code, password=OTHER_PASSWORD, **extra):
    return ac.post(
        "/api/auth/claim", json={"phone": PHONE, "country_code": "CI", "code": code, "password": password, **extra}
    )


async def _refresh_status(ac, pair):
    return (await ac.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code


@pytest.mark.asyncio
async def test_register_over_an_existing_account_changes_nothing(client):
    await make_user(PHONE, password=None, verified=True)
    victim = await _old_session()
    r = await _register(client)
    assert r.status_code == 202, r.text
    assert r.json() == CLAIM_ANSWER
    user = await _user()
    assert user.password_hash is None and user.phone_verified_at is not None
    assert await _refresh_status(client, victim) == 200
    # The squatter's password opens nothing.
    assert (await sign_in(client, PHONE, password=SQUATTER_PASSWORD)).status_code == 409


@pytest.mark.asyncio
async def test_suspended_account_gets_the_same_answer(client):
    await make_user(PHONE, password=None)
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()
        u.disabled = True
        await db.commit()
    r = await _register(client)
    assert r.status_code == 202 and r.json() == CLAIM_ANSWER
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.AccountCheck))).scalars().all() == []


@pytest.mark.asyncio
async def test_only_the_code_recipient_can_claim(client):
    await make_user(PHONE, password=None, verified=True)
    victim = await _old_session()
    assert (await _register(client, password=SQUATTER_PASSWORD)).status_code == 202
    assert (await _claim(client, "000000", password=SQUATTER_PASSWORD)).status_code == 401
    code = await send_open_check(PHONE, "verify_number")
    weak = await _claim(client, code, password="12345678")
    assert weak.status_code == 422
    r = await _claim(client, code, loyalty_consent_version="v2")
    assert r.status_code == 200, r.text
    pair = r.json()
    assert pair["verified"] is True and pair["must_change_password"] is False
    assert (await client.get("/api/customer/loyalty", headers=_auth(pair))).status_code == 200
    assert await _refresh_status(client, victim) == 401
    # The code is single use and the squatter's password never worked.
    assert (await _claim(client, code, password=SQUATTER_PASSWORD)).status_code == 401
    assert (await sign_in(client, PHONE, password=SQUATTER_PASSWORD)).status_code == 401
    assert (await sign_in(client, PHONE, password=OTHER_PASSWORD)).status_code == 200
    async with AsyncSessionLocal() as db:
        consent = (await db.execute(select(models.LoyaltyConsent))).scalars().one()
        assert consent.customer_id == phone_key(E164)


@pytest.mark.asyncio
async def test_claim_for_an_app_the_user_has_no_role_in(client):
    await make_user(PHONE, password=None)
    await _register(client)
    code = await send_open_check(PHONE, "verify_number")
    r = await _claim(client, code, app="merchant")
    assert r.status_code == 403
    assert (await sign_in(client, PHONE, password=OTHER_PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_register_with_a_password_is_still_refused(client):
    await make_user(PHONE)
    r = await _register(client)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_must_change_needs_the_pc_session(client):
    await make_user(PHONE)
    plain = (await sign_in(client, PHONE)).json()
    await client.post("/api/auth/password-reset", json={"phone": PHONE, "country_code": "CI"})
    temp = await send_open_check(PHONE, "reset_password")
    held = (await sign_in(client, PHONE, password=temp)).json()
    assert held["must_change_password"] is True
    r = await client.post("/api/auth/password", headers=_auth(plain), json={"new": SQUATTER_PASSWORD})
    assert r.status_code == 401
    r = await client.post("/api/auth/password", headers=_auth(plain), json={"current": WRONG_PASSWORD, "new": SQUATTER_PASSWORD})
    assert r.status_code == 401
    r = await client.post("/api/auth/password", headers=_auth(held), json={"new": OTHER_PASSWORD})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_password_change_kills_a_sent_temporary_password(client):
    await make_user(PHONE)
    pair = (await sign_in(client, PHONE)).json()
    await client.post("/api/auth/password-reset", json={"phone": PHONE, "country_code": "CI"})
    temp = await send_open_check(PHONE, "reset_password")
    r = await client.post(
        "/api/auth/password", headers=_auth(pair), json={"current": TEST_PASSWORD, "new": OTHER_PASSWORD}
    )
    assert r.status_code == 200, r.text
    assert (await sign_in(client, PHONE, password=temp)).status_code == 401


@pytest.mark.asyncio
async def test_temporary_password_login_signs_out_earlier_sessions(client):
    await make_user(PHONE)
    earlier = (await sign_in(client, PHONE)).json()
    await client.post("/api/auth/password-reset", json={"phone": PHONE, "country_code": "CI"})
    temp = await send_open_check(PHONE, "reset_password")
    held = (await sign_in(client, PHONE, password=temp)).json()
    assert await _refresh_status(client, earlier) == 401
    assert await _refresh_status(client, held) == 200


@pytest.mark.asyncio
async def test_verify_number_signs_out_earlier_sessions(client):
    r = await client.post(
        "/api/auth/register", json={"phone": PHONE, "country_code": "CI", "password": TEST_PASSWORD}
    )
    first = r.json()
    second = (await sign_in(client, PHONE)).json()
    code = await send_open_check(PHONE, "verify_number")
    r = await client.post("/api/auth/verify-number", headers=_auth(second), json={"code": code})
    assert r.status_code == 200, r.text
    assert await _refresh_status(client, first) == 401
    assert await _refresh_status(client, second) == 401
    assert await _refresh_status(client, r.json()) == 200


@pytest.mark.asyncio
async def test_number_correction_refused_for_an_account_with_roles_or_data(client):
    await make_user(PHONE, roles="customer,merchant", verified=False)
    pair = (await sign_in(client, PHONE)).json()
    assert pair["verified"] is False
    r = await client.post("/api/auth/number", headers=_auth(pair), json={"phone": "0705060708", "country_code": "CI"})
    assert r.status_code == 403 and r.json()["detail"] == "Contactez Fidelia pour changer de numero."

    other = "0702030405"
    await make_user(other, verified=False)
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
        db.add(models.LoyaltyEntry(customer_id=phone_key(normalize_phone(other, "CI")), venue_id=venue.id,
                                   points=10, reason="payment", created_at=utcnow()))
        await db.commit()
    pair = (await sign_in(client, other)).json()
    r = await client.post("/api/auth/number", headers=_auth(pair), json={"phone": "0705060708", "country_code": "CI"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_wrong_temporary_password_on_a_team_login_counts(client):
    await make_user(PHONE, password=None, verified=False)
    await client.post("/api/auth/password-reset", json={"phone": PHONE, "country_code": "CI"})
    temp = await send_open_check(PHONE, "reset_password")
    for _ in range(5):
        assert (await sign_in(client, PHONE, password=WRONG_PASSWORD)).status_code == 401
    assert (await sign_in(client, PHONE, password=temp)).status_code == 423
