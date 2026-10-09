"""Phone + one-time code sign-in, refresh rotation, and merchant gating.

The console sender with OTP_DEV_ECHO returns the code in the response, which
is how these tests (and a developer without a SIM) read the "SMS".
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data

PHONE = "07 12 34 56 78"
E164 = "+2250712345678"


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setenv("OTP_SENDER", "console")
    monkeypatch.setenv("OTP_DEV_ECHO", "1")
    monkeypatch.delenv("FIDELIA_ENV", raising=False)
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


async def _code(ac, phone=PHONE, app_name="customer"):
    r = await ac.post("/api/auth/otp/request", json={"phone": phone, "app": app_name})
    assert r.status_code == 202, r.text
    return r.json()["dev_code"]


async def _sign_in(ac, phone=PHONE, app_name="customer"):
    code = await _code(ac, phone, app_name)
    return await ac.post("/api/auth/otp/verify", json={"phone": phone, "code": code, "app": app_name})


async def _age_codes(seconds):
    """Moves every code back in time instead of sleeping through the cooldown."""
    async with AsyncSessionLocal() as db:
        for c in (await db.execute(select(models.OtpChallenge))).scalars():
            c.created_at -= timedelta(seconds=seconds)
            c.expires_at -= timedelta(seconds=seconds)
        await db.commit()


@pytest.mark.asyncio
async def test_customer_signs_in_with_phone_and_code(client):
    r = await _sign_in(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "customer"
    assert body["phone_masked"] == "07 •• •• 56 78"

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["sub"] == "tel:" + E164

    async with AsyncSessionLocal() as db:
        challenge = (await db.execute(select(models.OtpChallenge))).scalar_one()
        # Only an HMAC is stored, never the code.
        assert len(challenge.code_hash) == 64
        token = (await db.execute(select(models.RefreshToken))).scalar_one()
        assert body["refresh_token"] not in token.token_hash


@pytest.mark.asyncio
async def test_counter_points_follow_the_customer_into_the_app(client):
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
        db.add(models.LoyaltyEntry(customer_id="tel:" + E164, venue_id=venue.id, points=12, reason="payment",
                                   created_at=datetime.now()))
        await db.commit()
        venue_id = venue.id
    token = (await _sign_in(client)).json()["access_token"]
    r = await client.get(f"/api/venues/{venue_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["my_points"] >= 12


@pytest.mark.asyncio
async def test_wrong_code_is_refused_and_attempts_run_out(client):
    code = await _code(client)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": wrong})
        assert r.status_code == 401
    # Five guesses spent: even the right code no longer works.
    r = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_code_is_single_use_and_expires(client):
    code = await _code(client)
    assert (await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code})).status_code == 200
    assert (await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code})).status_code == 401

    await _age_codes(120)
    code = await _code(client)
    await _age_codes(301)
    assert (await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code})).status_code == 401


@pytest.mark.asyncio
async def test_resend_cooldown_and_hourly_cap(client):
    await _code(client)
    r = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    for _ in range(4):
        await _age_codes(61)
        await _code(client)
    await _age_codes(61)
    assert (await client.post("/api/auth/otp/request", json={"phone": PHONE})).status_code == 429


@pytest.mark.asyncio
async def test_new_code_voids_the_previous_one(client):
    first = await _code(client)
    await _age_codes(61)
    second = await _code(client)
    if first != second:
        assert (await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": first})).status_code == 401
    assert (await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": second})).status_code == 200


@pytest.mark.asyncio
async def test_invalid_phone_is_refused(client):
    r = await client.post("/api/auth/otp/request", json={"phone": "12345"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_refresh_rotates_and_reuse_kills_the_session(client):
    first = (await _sign_in(client)).json()
    r = await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]

    # The old token again: someone copied it. Both copies die.
    assert (await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": second["refresh_token"]})).status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh(client):
    pair = (await _sign_in(client)).json()
    assert (await client.post("/api/auth/logout", json={"refresh_token": pair["refresh_token"]})).status_code == 204
    assert (await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401


@pytest.mark.asyncio
async def test_merchant_session_needs_the_merchant_role(client):
    r = await _sign_in(client, app_name="merchant")
    assert r.status_code == 403

    admin = (await client.post("/api/token", data={"username": "admin", "password": "admin123"})).json()["access_token"]
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue).where(models.Venue.owner_username.is_(None)))).scalars().first()
        venue_id = venue.id
    r = await client.post(
        "/api/admin/users/roles",
        json={"phone": PHONE, "role": "merchant", "venue_id": venue_id},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["roles"] == ["merchant"]

    await _age_codes(61)
    r = await _sign_in(client, app_name="merchant")
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    # The token runs the venue it was linked to.
    r = await client.get("/api/merchant/venue/location", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text

    # The same person can also shop: a customer session adds the role.
    await _age_codes(61)
    assert (await _sign_in(client)).status_code == 200
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()
        assert user.role_set() == {"customer", "merchant"}


@pytest.mark.asyncio
async def test_seeded_dev_merchant_signs_in_to_its_venue(client):
    r = await _sign_in(client, phone="07 00 00 00 02", app_name="merchant")
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/merchant/venue/location", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_only_admin_grants_roles(client):
    customer = (await _sign_in(client)).json()["access_token"]
    r = await client.post(
        "/api/admin/users/roles", json={"phone": PHONE, "role": "admin"},
        headers={"Authorization": f"Bearer {customer}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_disabled_user_cannot_sign_in_or_refresh(client):
    pair = (await _sign_in(client)).json()
    async with AsyncSessionLocal() as db:
        await db.execute(update(models.User).where(models.User.phone_e164 == E164).values(disabled=True))
        await db.commit()
    assert (await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401
    await _age_codes(61)
    assert (await _sign_in(client)).status_code == 403


@pytest.mark.asyncio
async def test_production_refuses_console_codes_and_demo_login(client, monkeypatch):
    monkeypatch.setenv("FIDELIA_ENV", "production")
    with pytest.raises(RuntimeError):
        await client.post("/api/auth/otp/request", json={"phone": PHONE})
    r = await client.post("/api/token", data={"username": "demo", "password": "demo123"})
    assert r.status_code == 404


TEST_NUMBERS = "+2250700000001:000000,07 00 00 00 02:000000"


@pytest.mark.asyncio
async def test_shared_test_numbers_sign_in_with_their_fixed_code(client, monkeypatch):
    monkeypatch.setenv("FIDELIA_ENV", "test")
    monkeypatch.setenv("OTP_DEV_ECHO", "0")
    monkeypatch.setenv("TEST_OTP_NUMBERS", TEST_NUMBERS)

    # Many testers share the number: repeated requests are never throttled,
    # and an earlier request's code still works after a later one.
    for _ in range(7):
        assert (await client.post("/api/auth/otp/request", json={"phone": "0700000001"})).status_code == 202
    bad = await client.post("/api/auth/otp/verify", json={"phone": "0700000001", "code": "123456"})
    assert bad.status_code == 401
    for _ in range(2):
        r = await client.post("/api/auth/otp/verify", json={"phone": "0700000001", "code": "000000"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "customer"

    # The seeded merchant number opens the merchant app with the same code.
    r = await client.post("/api/auth/otp/verify", json={"phone": "0700000002", "code": "000000", "app": "merchant"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "merchant"

    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.OtpChallenge))).scalars().all() == []

    # Any other number still needs a real code.
    other = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "code": "000000"})
    assert other.status_code == 401


@pytest.mark.asyncio
async def test_test_numbers_only_apply_in_the_test_environment(client, monkeypatch):
    monkeypatch.setenv("TEST_OTP_NUMBERS", TEST_NUMBERS)
    # Unset FIDELIA_ENV (local development): ignored.
    r = await client.post("/api/auth/otp/verify", json={"phone": "0700000001", "code": "000000"})
    assert r.status_code == 401

    monkeypatch.setenv("FIDELIA_ENV", "production")
    with pytest.raises(RuntimeError):
        await client.post("/api/auth/otp/verify", json={"phone": "0700000001", "code": "000000"})

    monkeypatch.setenv("FIDELIA_ENV", "test")
    monkeypatch.setenv("TEST_OTP_NUMBERS", "+2250700000001:123")
    with pytest.raises(RuntimeError):
        await client.post("/api/auth/otp/verify", json={"phone": "0700000001", "code": "000000"})


@pytest.mark.asyncio
async def test_consent_ticked_on_the_sign_in_screen_is_recorded(client):
    code = await _code(client)
    r = await client.post("/api/auth/otp/verify", json={
        "phone": PHONE, "code": code, "app": "customer", "loyalty_consent_version": "fidelite-2026-10"})
    assert r.status_code == 200
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(models.LoyaltyConsent))).scalar_one()
        assert row.customer_id == "tel:" + E164 and row.source == "app"
        assert row.consent_version == "fidelite-2026-10"


@pytest.mark.asyncio
async def test_signing_in_without_ticking_opens_the_account_without_consent(client):
    assert (await _sign_in(client)).status_code == 200
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.LoyaltyConsent))).first() is None
