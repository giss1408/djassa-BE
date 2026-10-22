"""Unverified and must-change sessions reach only the routes they need."""

import re
from urllib.parse import unquote

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api.auth import utcnow
from app.core.phone import normalize_phone, phone_key
from app.core.security import create_access_token
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from app.services import account_checks

PHONE = "0701020304"
E164 = normalize_phone(PHONE, "CI")
NEW_PHONE = "0705060708"
NEW_E164 = normalize_phone(NEW_PHONE, "CI")


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


async def _register(ac, **extra):
    r = await ac.post(
        "/api/auth/register",
        json={"phone": PHONE, "country_code": "CI", "password": "motdepasse1", "app": "customer", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _send_code(e164=E164):
    """What the admin app does: send the check, read the code from the link."""
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one()
        check = (
            await db.execute(
                select(models.AccountCheck).where(
                    models.AccountCheck.user_id == user.id,
                    models.AccountCheck.kind == "verify_number",
                    models.AccountCheck.status.in_(("pending", "sent")),
                )
            )
        ).scalars().first()
        link = await account_checks.send_check(db, check, 1, utcnow())
        await db.commit()
    match = re.search(r"(\d{3}) (\d{3})", unquote(link).replace("+", " "))
    return match.group(1) + match.group(2)


async def _give_points(e164):
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
        db.add(
            models.LoyaltyEntry(
                customer_id=phone_key(e164), venue_id=venue.id, points=40, reason="payment", created_at=utcnow()
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_unverified_session_sees_no_points(client):
    await _give_points(E164)
    pair = await _register(client)
    r = await client.get("/api/customer/loyalty", headers=_auth(pair))
    assert r.status_code == 403 and r.json()["detail"] == "number_not_verified"
    r = await client.post("/api/customer/payments", headers=_auth(pair), json={})
    assert r.status_code == 403 and r.json()["detail"] == "number_not_verified"


@pytest.mark.asyncio
async def test_unverified_session_can_read_me_and_log_out(client):
    pair = await _register(client)
    r = await client.get("/api/auth/me", headers=_auth(pair))
    assert r.status_code == 200
    assert r.json()["verified"] is False and r.json()["must_change_password"] is False
    r = await client.post("/api/auth/logout", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_unverified_session_browses_the_catalogue_as_anonymous(client):
    pair = await _register(client)
    r = await client.get("/api/venues", headers=_auth(pair))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_must_change_session_is_held(client):
    token = create_access_token({"sub": phone_key(E164), "role": "customer", "vf": True, "pc": True})
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.get("/api/customer/loyalty", headers=headers)
    assert r.status_code == 403 and r.json()["detail"] == "password_change_required"
    r = await client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200 and r.json()["must_change_password"] is True


@pytest.mark.asyncio
async def test_code_from_the_team_verifies_the_number(client):
    await _give_points(E164)
    pair = await _register(client)
    code = await _send_code()
    bad = await client.post("/api/auth/verify-number", headers=_auth(pair), json={"code": "000000"})
    assert bad.status_code == 401 and bad.json()["detail"] == "Code incorrect ou expire."
    r = await client.post("/api/auth/verify-number", headers=_auth(pair), json={"code": code})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["verified"] is True
    r = await client.get("/api/customer/loyalty", headers=_auth(new))
    assert r.status_code == 200
    assert r.json()["venues"][0]["points"] == 40
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()
        assert user.phone_verified_at is not None


@pytest.mark.asyncio
async def test_consent_given_at_sign_up_is_recorded_on_verification(client):
    pair = await _register(client, loyalty_consent_version="v1")
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.LoyaltyConsent))).scalars().first() is None
    code = await _send_code()
    r = await client.post("/api/auth/verify-number", headers=_auth(pair), json={"code": code})
    assert r.status_code == 200, r.text
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(models.LoyaltyConsent))).scalars().one()
        assert row.customer_id == phone_key(E164) and row.consent_version == "v1"
        assert row.withdrawn_at is None


@pytest.mark.asyncio
async def test_unverified_user_can_correct_the_number(client):
    pair = await _register(client)
    old_code = await _send_code()
    r = await client.post(
        "/api/auth/number", headers=_auth(pair), json={"phone": NEW_PHONE, "country_code": "CI"}
    )
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["verified"] is False
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == NEW_E164))).scalar_one()
        assert user.phone_verified_at is None
        assert (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one_or_none() is None
    # The old refresh token is gone, and the code sent to the old number is dead.
    r = await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 401
    r = await client.post("/api/auth/verify-number", headers=_auth(new), json={"code": old_code})
    assert r.status_code == 401
    code = await _send_code(NEW_E164)
    r = await client.post("/api/auth/verify-number", headers=_auth(new), json={"code": code})
    assert r.status_code == 200 and r.json()["verified"] is True
    # Verified accounts cannot use it.
    r = await client.post(
        "/api/auth/number", headers=_auth(r.json()), json={"phone": "0709090909", "country_code": "CI"}
    )
    assert r.status_code == 403 and r.json()["detail"] == "Ce numero est deja verifie."


@pytest.mark.asyncio
async def test_correcting_to_a_taken_number_is_a_conflict(client):
    from tests.helpers import make_user

    await make_user(NEW_PHONE)
    pair = await _register(client)
    r = await client.post(
        "/api/auth/number", headers=_auth(pair), json={"phone": NEW_PHONE, "country_code": "CI"}
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_old_tokens_without_vf_still_work(client):
    token = create_access_token({"sub": phone_key(E164), "role": "customer"})
    r = await client.get("/api/customer/loyalty", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["verified"] is True and r.json()["must_change_password"] is False


@pytest.mark.asyncio
async def test_held_merchant_token_reads_no_sales_over_graphql_or_usage(client):
    from app.api.usage_events import _merchant_venue_id
    from starlette.requests import Request

    for claims in ({"vf": True, "pc": True}, {"vf": False, "pc": False}):
        token = create_access_token({"sub": "demo", "role": "merchant", **claims})
        r = await client.post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "{ mySales(limit: 5) { source } }"},
        )
        assert "Authentication required" in r.text and not (r.json().get("data") or {}).get("mySales")
        scope = {"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]}
        async with AsyncSessionLocal() as db:
            assert await _merchant_venue_id(Request(scope), db) is None
    ok = create_access_token({"sub": "demo", "role": "merchant"})
    scope = {"type": "http", "headers": [(b"authorization", f"Bearer {ok}".encode())]}
    async with AsyncSessionLocal() as db:
        assert await _merchant_venue_id(Request(scope), db) is not None


@pytest.mark.asyncio
async def test_correcting_to_the_same_number_is_refused(client):
    pair = await _register(client)
    r = await client.post("/api/auth/number", headers=_auth(pair), json={"phone": PHONE, "country_code": "CI"})
    assert r.status_code == 422 and r.json()["detail"] == "C'est deja le numero de ce compte"
