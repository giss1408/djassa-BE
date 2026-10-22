"""Account recovery: sign out elsewhere, change number, lost number.

The account is the phone number, so recovery is moving everything a person
owns from one `tel:` key to another, and making sure the old number, and any
phone signed in on it, is left with nothing.
"""

from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String, select

from tests.helpers import demo_login
from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from app.services.account_move import AUDIT, OWNED
from tests.helpers import arm, make_user, send_open_check, sign_in

OLD = "07 12 34 56 78"
OLD_E164 = "+2250712345678"
NEW = "05 11 22 33 44"
NEW_E164 = "+2250511223344"
MERCHANT = "07 00 00 00 02"  # seeded: runs "Chez Tantie Awa (exemple)"


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


async def _sign_in(ac, phone=OLD, app_name="customer", password="motdepasse1"):
    r = await sign_in(ac, phone, app_name, password)
    assert r.status_code == 200, r.text
    return r.json()


def _h(pair):
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def _admin(ac):
    r = await demo_login(ac, data={"username": "admin", "password": "admin123"})
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
        ("account_checks", "sent_by"),  # a team member's name, not a tel: key
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
    await make_user(OLD)
    lost_phone = await _sign_in(client)
    this_phone = await _sign_in(client)

    r = await client.post("/api/auth/sessions/revoke-others", json={"refresh_token": this_phone["refresh_token"]}, headers=_h(this_phone))
    assert r.json() == {"revoked": 1}
    assert (await client.post("/api/auth/refresh", json={"refresh_token": lost_phone["refresh_token"]})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": this_phone["refresh_token"]})).status_code == 200


@pytest.mark.asyncio
async def test_demo_accounts_have_nothing_to_recover(client):
    r = await demo_login(client, data={"username": "client", "password": "client123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.post("/api/auth/sessions/revoke-others", json={}, headers=h)).status_code == 403


async def _request_change(ac, pair, password="motdepasse1", new_phone=NEW):
    return await ac.post(
        "/api/auth/change-number/request",
        json={"password": password, "new_phone": new_phone, "country_code": "CI"}, headers=_h(pair),
    )


@pytest.mark.asyncio
async def test_change_number_needs_the_password_and_the_code_on_the_new_number(client):
    await make_user(OLD)
    venue_id = await _give_points(OLD_E164)
    other_device = await _sign_in(client)
    pair = await _sign_in(client)

    # A session left unlocked is not enough: the password is asked again.
    r = await _request_change(client, pair, password="mauvaismdp1")
    assert r.status_code == 401 and r.json()["detail"] == "Mot de passe incorrect."
    r = await _request_change(client, pair)
    assert r.status_code == 202, r.text
    assert r.json() == {"new_phone_masked": "05 •• •• 33 44"}

    # No code sent yet, then a wrong one: nothing moves.
    body = {"code": "123456"}
    assert (await client.post("/api/auth/change-number/confirm", json=body, headers=_h(pair))).status_code == 401
    code = await send_open_check(OLD, "change_number")
    assert (await client.post("/api/auth/change-number/confirm", json={"code": "000000"}, headers=_h(pair))).status_code == 401

    r = await client.post("/api/auth/change-number/confirm", json={"code": code}, headers=_h(pair))
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
    # The old number has no account any more.
    assert (await sign_in(client, OLD)).status_code == 401
    assert (await sign_in(client, NEW)).status_code == 200

    async with AsyncSessionLocal() as db:
        change = (await db.execute(select(models.AccountNumberChange))).scalar_one()
        assert (change.old_phone_e164, change.new_phone_e164, change.method) == (OLD_E164, NEW_E164, "self_service")


@pytest.mark.asyncio
async def test_change_number_needs_a_free_number_that_is_not_the_same(client):
    await make_user(OLD)
    await make_user(NEW)
    pair = await _sign_in(client)
    assert (await _request_change(client, pair)).status_code == 409
    assert (await _request_change(client, pair, new_phone=OLD)).status_code == 422


@pytest.mark.asyncio
async def test_change_number_taken_meanwhile_is_refused_at_confirm(client):
    await make_user(OLD)
    pair = await _sign_in(client)
    assert (await _request_change(client, pair)).status_code == 202
    code = await send_open_check(OLD, "change_number")
    await make_user(NEW)
    r = await client.post("/api/auth/change-number/confirm", json={"code": code}, headers=_h(pair))
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_a_code_sent_to_one_new_number_cannot_move_the_account_to_another(client):
    await make_user(OLD)
    pair = await _sign_in(client)
    assert (await _request_change(client, pair)).status_code == 202
    code = await send_open_check(OLD, "change_number")
    assert (await _request_change(client, pair, new_phone="05 99 88 77 66")).status_code == 202
    r = await client.post("/api/auth/change-number/confirm", json={"code": code}, headers=_h(pair))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_change_number_code_is_not_a_login_or_verification_code(client):
    await make_user(OLD)
    pair = await _sign_in(client)
    await _request_change(client, pair)
    code = await send_open_check(OLD, "change_number")
    r = await client.post("/api/auth/verify-number", json={"code": code}, headers=_h(pair))
    assert r.status_code == 401


async def _file(ac, pair, old=MERCHANT, details="Mon maquis s'appelle Chez Tantie Awa, a Yopougon."):
    return await ac.post("/api/auth/recovery", json={"old_phone": old, "details": details}, headers=_h(pair))


@pytest.mark.asyncio
async def test_recovery_needs_a_verified_new_number(client):
    await arm(MERCHANT)
    # The new number is registered but the team has not checked it yet.
    r = await client.post("/api/auth/register", json={"phone": NEW, "password": "motdepasse1", "app": "customer"})
    assert r.status_code == 201
    unverified = r.json()
    r = await _file(client, unverified)
    assert r.status_code == 403 and r.json()["detail"] == "number_not_verified"
    assert (await client.post("/api/auth/recovery", json={"old_phone": MERCHANT, "details": "Mon numero a ete vole hier."})).status_code == 401

    code = await send_open_check(NEW, "verify_number")
    verified = (await client.post("/api/auth/verify-number", json={"code": code}, headers=_h(unverified))).json()
    assert (await _file(client, verified)).status_code == 202
    # Same number as the session, or one request at a time.
    assert (await _file(client, verified, old=NEW)).status_code == 422
    assert (await _file(client, verified, details="Encore moi, meme demande.")).status_code == 409


@pytest.mark.asyncio
async def test_merchant_recovers_shop_after_losing_number(client):
    await arm(MERCHANT)
    merchant = await _sign_in(client, MERCHANT, "merchant")
    await _give_points("+2250700000002", 5)
    await make_user(NEW, password="nouveaumdp9")
    new = await _sign_in(client, NEW, password="nouveaumdp9")
    assert (await _file(client, new)).status_code == 202

    admin = await _admin(client)
    pending = (await client.get("/api/admin/recovery-requests", headers=admin)).json()
    assert len(pending) == 1
    request = pending[0]
    assert request["new_phone"] == NEW_E164
    assert request["old_account"]["roles"] == ["merchant"]
    assert request["old_account"]["venues_owned"] == ["Chez Tantie Awa (exemple)"]

    r = await client.post(f"/api/admin/recovery-requests/{request['id']}/approve", json={"note": "Appel, OK"}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert (await client.post(f"/api/admin/recovery-requests/{request['id']}/approve", json={}, headers=admin)).status_code == 409

    # The lost phone's session is over; the new number runs the shop, with the
    # password and proven number the person registered it with.
    assert (await client.post("/api/auth/refresh", json={"refresh_token": merchant["refresh_token"]})).status_code == 401
    assert (await sign_in(client, MERCHANT, "merchant")).status_code == 401
    recovered = await sign_in(client, NEW, "merchant", password="nouveaumdp9")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["verified"] is True
    assert (await client.get("/api/merchant/venue/location", headers=_h(recovered.json()))).status_code == 200
    async with AsyncSessionLocal() as db:
        assert len((await db.execute(select(models.User).where(models.User.phone_e164 == NEW_E164))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_recovery_is_refused_when_the_new_number_already_owns_something(client):
    await arm(MERCHANT)
    await make_user(NEW)
    await _give_points(NEW_E164, 7)
    new = await _sign_in(client, NEW)
    assert (await _file(client, new)).status_code == 202
    admin = await _admin(client)
    request = (await client.get("/api/admin/recovery-requests", headers=admin)).json()[0]
    r = await client.post(f"/api/admin/recovery-requests/{request['id']}/approve", json={}, headers=admin)
    assert r.status_code == 409


async def _filed_for_merchant(client, consent=None):
    """The merchant's account, a registered and verified placeholder on NEW, a filed request."""
    await arm(MERCHANT)
    r = await client.post("/api/auth/register", json={
        "phone": NEW, "password": "nouveaumdp9", "app": "customer", **({"loyalty_consent_version": consent} if consent else {}),
    })
    unverified = r.json()
    code = await send_open_check(NEW, "verify_number")
    verified = (await client.post("/api/auth/verify-number", json={"code": code}, headers=_h(unverified))).json()
    assert (await _file(client, verified)).status_code == 202
    admin = await _admin(client)
    request = (await client.get("/api/admin/recovery-requests", headers=admin)).json()[0]
    return admin, request["id"]


@pytest.mark.asyncio
async def test_approve_takes_a_verified_placeholder_and_keeps_its_consent(client):
    admin, rid = await _filed_for_merchant(client, consent="v1")
    r = await client.post(f"/api/admin/recovery-requests/{rid}/approve", json={}, headers=admin)
    assert r.status_code == 200, r.text
    async with AsyncSessionLocal() as db:
        consent = (await db.execute(select(models.LoyaltyConsent).where(models.LoyaltyConsent.customer_id == "tel:" + NEW_E164))).scalar_one()
        assert consent.consent_version == "v1" and consent.withdrawn_at is None
    assert (await sign_in(client, NEW, "merchant", password="nouveaumdp9")).status_code == 200


@pytest.mark.asyncio
async def test_approve_refuses_a_placeholder_that_is_not_the_filer(client):
    admin, rid = await _filed_for_merchant(client)
    # The filer's account goes away and someone else registers the number.
    async with AsyncSessionLocal() as db:
        filer = (await db.execute(select(models.User).where(models.User.phone_e164 == NEW_E164))).scalar_one()
        filer.phone_e164 = "+2250500000000"
        await db.commit()
    await make_user(NEW, password="autremdp123")
    r = await client.post(f"/api/admin/recovery-requests/{rid}/approve", json={}, headers=admin)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_approve_refuses_an_unverified_placeholder(client):
    admin, rid = await _filed_for_merchant(client)
    async with AsyncSessionLocal() as db:
        filer = (await db.execute(select(models.User).where(models.User.phone_e164 == NEW_E164))).scalar_one()
        filer.phone_verified_at = None
        await db.commit()
    r = await client.post(f"/api/admin/recovery-requests/{rid}/approve", json={}, headers=admin)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_recovery_does_not_reveal_who_has_an_account(client):
    await make_user(NEW)
    new = await _sign_in(client, NEW)
    r = await _file(client, new, old="07 99 99 99 99", details="Je ne sais plus trop quoi dire.")
    assert r.status_code == 202
    admin = await _admin(client)
    request = (await client.get("/api/admin/recovery-requests", headers=admin)).json()[0]
    assert request["old_account"] is None
    # Nothing to move: the admin can only reject.
    assert (await client.post(f"/api/admin/recovery-requests/{request['id']}/approve", json={}, headers=admin)).status_code == 409
    r = await client.post(f"/api/admin/recovery-requests/{request['id']}/reject", json={"note": "Aucun compte"}, headers=admin)
    assert r.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_the_code_endpoint_for_recovery_is_gone(client):
    assert (await client.post("/api/auth/recovery/code", json={"new_phone": NEW})).status_code == 404


@pytest.mark.asyncio
async def test_only_admins_review_and_revoke(client):
    await make_user(OLD)
    pair = await _sign_in(client)
    assert (await client.get("/api/admin/recovery-requests", headers=_h(pair))).status_code == 403
    assert (await client.post("/api/admin/users/revoke-sessions", json={"phone": OLD}, headers=_h(pair))).status_code == 403

    r = await client.post("/api/admin/users/revoke-sessions", json={"phone": OLD}, headers=await _admin(client))
    assert r.json() == {"revoked": 1}
    assert (await client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401
