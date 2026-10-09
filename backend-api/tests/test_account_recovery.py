"""Account recovery: sign out elsewhere, change number, lost number.

The account is the phone number, so recovery is moving everything a person
owns from one `tel:` key to another, and making sure the old number, and any
phone signed in on it, is left with nothing.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String, select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from app.services.account_move import AUDIT, OWNED

OLD = "07 12 34 56 78"
OLD_E164 = "+2250712345678"
NEW = "05 11 22 33 44"
NEW_E164 = "+2250511223344"


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


async def _age_codes(seconds=61):
    async with AsyncSessionLocal() as db:
        for c in (await db.execute(select(models.OtpChallenge))).scalars():
            c.created_at -= timedelta(seconds=seconds)
        await db.commit()


async def _sign_in(ac, phone=OLD, app_name="customer"):
    r = await ac.post("/api/auth/otp/request", json={"phone": phone, "app": app_name})
    assert r.status_code == 202, r.text
    r = await ac.post("/api/auth/otp/verify", json={"phone": phone, "code": r.json()["dev_code"], "app": app_name})
    assert r.status_code == 200, r.text
    return r.json()


def _h(pair):
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def _admin(ac):
    r = await ac.post("/api/token", data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _give_points(e164, points=40):
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
        db.add(models.LoyaltyEntry(customer_id="tel:" + e164, venue_id=venue.id, points=points, reason="payment",
                                   created_at=datetime.now()))
        await db.commit()
        return venue.id


def test_every_account_key_column_is_classified():
    """A new column holding a `tel:` key must say whether it follows the
    person to a new number (OWNED) or records history (AUDIT)."""
    known = {(m.__tablename__, c) for m, c in OWNED + AUDIT}
    not_accounts = {
        ("payments", "recipient_id"), ("payments", "idempotency_key"), ("payment_refunds", "idempotency_key"),
        ("transactions", "idempotency_key"), ("identity_profiles", "verification_provider"),
    }
    unclassified = [
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, String) and column.type.length == 128
        and (table.name, column.name) not in known | not_accounts
    ]
    assert unclassified == []


@pytest.mark.asyncio
async def test_sign_out_other_devices_keeps_this_one(client):
    lost_phone = await _sign_in(client)
    await _age_codes()
    this_phone = await _sign_in(client)

    r = await client.post("/api/auth/sessions/revoke-others", json={"refresh_token": this_phone["refresh_token"]}, headers=_h(this_phone))
    assert r.json() == {"revoked": 1}
    assert (await client.post("/api/auth/refresh", json={"refresh_token": lost_phone["refresh_token"]})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": this_phone["refresh_token"]})).status_code == 200


@pytest.mark.asyncio
async def test_demo_accounts_have_nothing_to_recover(client):
    r = await client.post("/api/token", data={"username": "client", "password": "client123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/api/auth/sessions/revoke-others", json={}, headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_change_number_moves_points_and_ends_old_sessions(client):
    venue_id = await _give_points(OLD_E164)
    other_device = await _sign_in(client)
    await _age_codes()
    pair = await _sign_in(client)
    await _age_codes()

    r = await client.post("/api/auth/change-number/request", json={"new_phone": NEW}, headers=_h(pair))
    assert r.status_code == 202, r.text
    codes = r.json()
    assert codes["new_phone_masked"] == "05 •• •• 33 44"

    r = await client.post(
        "/api/auth/change-number/confirm",
        json={"new_phone": NEW, "old_code": codes["dev_old_code"], "new_code": codes["dev_new_code"]},
        headers=_h(pair),
    )
    assert r.status_code == 200, r.text
    fresh = r.json()
    me = (await client.get("/api/auth/me", headers=_h(fresh))).json()
    assert me["sub"] == "tel:" + NEW_E164

    # Points followed the person.
    venue = (await client.get(f"/api/venues/{venue_id}", headers=_h(fresh))).json()
    assert venue["my_points"] >= 40
    # Every earlier session, on any device, is over.
    for old in (pair, other_device):
        assert (await client.post("/api/auth/refresh", json={"refresh_token": old["refresh_token"]})).status_code == 401
    # The old number now opens an empty account.
    await _age_codes(400)
    stranger = await _sign_in(client, OLD)
    assert (await client.get(f"/api/venues/{venue_id}", headers=_h(stranger))).json()["my_points"] == 0

    async with AsyncSessionLocal() as db:
        change = (await db.execute(select(models.AccountNumberChange))).scalar_one()
        assert (change.old_phone_e164, change.new_phone_e164, change.method) == (OLD_E164, NEW_E164, "self_service")


@pytest.mark.asyncio
async def test_change_number_needs_both_codes_and_a_free_number(client):
    pair = await _sign_in(client)
    await _age_codes()
    codes = (await client.post("/api/auth/change-number/request", json={"new_phone": NEW}, headers=_h(pair))).json()

    # A sign-in code is not a change-number code, and one SIM is not enough.
    r = await client.post(
        "/api/auth/change-number/confirm",
        json={"new_phone": NEW, "old_code": codes["dev_new_code"], "new_code": codes["dev_new_code"]},
        headers=_h(pair),
    )
    if codes["dev_new_code"] != codes["dev_old_code"]:
        assert r.status_code == 401

    # Someone already uses the new number.
    await _age_codes()
    await _sign_in(client, NEW)
    r = await client.post("/api/auth/change-number/request", json={"new_phone": NEW}, headers=_h(pair))
    assert r.status_code == 409

    r = await client.post("/api/auth/change-number/request", json={"new_phone": OLD}, headers=_h(pair))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_change_number_code_cannot_sign_in(client):
    pair = await _sign_in(client)
    await _age_codes()
    codes = (await client.post("/api/auth/change-number/request", json={"new_phone": NEW}, headers=_h(pair))).json()
    r = await client.post("/api/auth/otp/verify", json={"phone": NEW, "code": codes["dev_new_code"]})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_merchant_recovers_shop_after_losing_number(client):
    # 07 00 00 00 02 runs a seeded shop (app/seed.py).
    merchant = await _sign_in(client, "07 00 00 00 02", "merchant")
    await _give_points("+2250700000002", 5)

    code = (await client.post("/api/auth/recovery/code", json={"new_phone": NEW})).json()["dev_code"]
    r = await client.post("/api/auth/recovery", json={
        "new_phone": NEW, "code": code, "old_phone": "07 00 00 00 02",
        "details": "Mon maquis s'appelle Chez Tantie Awa, a Yopougon.",
    })
    assert r.status_code == 202, r.text
    # One pending request per new number.
    await _age_codes()
    code = (await client.post("/api/auth/recovery/code", json={"new_phone": NEW})).json()["dev_code"]
    again = await client.post("/api/auth/recovery", json={
        "new_phone": NEW, "code": code, "old_phone": "07 00 00 00 02", "details": "Encore moi, meme demande.",
    })
    assert again.status_code == 409

    admin = await _admin(client)
    pending = (await client.get("/api/admin/recovery-requests", headers=admin)).json()
    assert len(pending) == 1
    request = pending[0]
    assert request["old_account"]["roles"] == ["merchant"]
    assert request["old_account"]["venues_owned"] == ["Chez Tantie Awa (exemple)"]

    r = await client.post(f"/api/admin/recovery-requests/{request['id']}/approve", json={"note": "Appel, OK"}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert (await client.post(f"/api/admin/recovery-requests/{request['id']}/approve", json={}, headers=admin)).status_code == 409

    # The lost phone's session is over; the new number runs the shop.
    assert (await client.post("/api/auth/refresh", json={"refresh_token": merchant["refresh_token"]})).status_code == 401
    await _age_codes(400)
    recovered = await _sign_in(client, NEW, "merchant")
    assert (await client.get("/api/merchant/venue/location", headers=_h(recovered))).status_code == 200


@pytest.mark.asyncio
async def test_recovery_does_not_reveal_who_has_an_account(client):
    code = (await client.post("/api/auth/recovery/code", json={"new_phone": NEW})).json()["dev_code"]
    r = await client.post("/api/auth/recovery", json={
        "new_phone": NEW, "code": code, "old_phone": "07 99 99 99 99", "details": "Je ne sais plus trop quoi dire.",
    })
    assert r.status_code == 202
    admin = await _admin(client)
    request = (await client.get("/api/admin/recovery-requests", headers=admin)).json()[0]
    assert request["old_account"] is None
    # Nothing to move: the admin can only reject.
    assert (await client.post(f"/api/admin/recovery-requests/{request['id']}/approve", json={}, headers=admin)).status_code == 409
    r = await client.post(f"/api/admin/recovery-requests/{request['id']}/reject", json={"note": "Aucun compte"}, headers=admin)
    assert r.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_recovery_needs_the_new_number_code(client):
    r = await client.post("/api/auth/recovery", json={
        "new_phone": NEW, "code": "123456", "old_phone": OLD, "details": "Mon numero a ete vole hier.",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_only_admins_review_and_revoke(client):
    pair = await _sign_in(client)
    assert (await client.get("/api/admin/recovery-requests", headers=_h(pair))).status_code == 403
    assert (await client.post("/api/admin/users/revoke-sessions", json={"phone": OLD}, headers=_h(pair))).status_code == 403

    r = await client.post("/api/admin/users/revoke-sessions", json={"phone": OLD}, headers=await _admin(client))
    assert r.json() == {"revoked": 1}
    assert (await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401
