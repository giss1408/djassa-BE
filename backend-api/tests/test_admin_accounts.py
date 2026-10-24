"""Admin routes the Fidelia Admin app uses to send WhatsApp checks and look after accounts."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from tests.helpers import OTHER_PASSWORD, make_user, sign_in

ADMIN = "07 99 00 00 01"
AGENT = "07 99 00 00 02"
SHOPPER = "07 12 34 56 78"
SHOPPER_E164 = "+2250712345678"
OWNER = "07 12 34 56 79"
NEWBIE = "07 12 34 56 80"
BASE = "/api/admin/accounts"


@pytest_asyncio.fixture
async def client():
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


async def _h(ac, phone, app_name):
    r = await sign_in(ac, phone, app_name)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _admin(ac):
    await make_user(ADMIN, roles="customer,admin")
    return await _h(ac, ADMIN, "admin")


async def _user_id(e164):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.User.id).where(models.User.phone_e164 == e164))).scalar_one()


async def _open(e164, kind, **kw):
    from app.api.auth import utcnow
    from app.services import account_checks

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one()
        check = await account_checks.open_check(db, user, kind, utcnow(), **kw)
        await db.commit()
        return check.id


async def _actions():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.AdminAction).order_by(models.AdminAction.id))).scalars().all()


@pytest.mark.asyncio
async def test_only_admins_reach_these_routes(client):
    await make_user(SHOPPER)
    await make_user(OWNER, roles="customer,merchant")
    await make_user(AGENT, roles="customer,agent")
    heads = [
        await _h(client, SHOPPER, "customer"),
        await _h(client, OWNER, "merchant"),
        await _h(client, AGENT, "admin"),
    ]
    for h in heads:
        assert (await client.get(f"{BASE}/checks", headers=h)).status_code == 403
        assert (await client.get(f"{BASE}/users", params={"phone": SHOPPER}, headers=h)).status_code == 403
        assert (await client.post(f"{BASE}/users/1/suspend", headers=h)).status_code == 403
    assert (await client.get(f"{BASE}/checks")).status_code == 401


@pytest.mark.asyncio
async def test_lists_mask_the_number(client):
    h = await _admin(client)
    await make_user(SHOPPER, verified=False)
    await make_user(OWNER, roles="customer,merchant")
    first = await _open(SHOPPER_E164, "verify_number")
    second = await _open("+2250712345679", "reset_password", team_created=True)
    r = await client.get(f"{BASE}/checks", headers=h)
    assert r.status_code == 200
    rows = r.json()
    assert [x["id"] for x in rows] == [first, second]
    assert rows[0]["phone_masked"] != SHOPPER_E164 and "345678" not in rows[0]["phone_masked"]
    assert rows[0]["app"] == "customer" and rows[0]["team_created"] is False
    assert rows[1]["app"] == "merchant" and rows[1]["team_created"] is True
    only = await client.get(f"{BASE}/checks", params={"kind": "reset_password"}, headers=h)
    assert [x["id"] for x in only.json()] == [second]
    u = await client.get(f"{BASE}/users", params={"phone": SHOPPER}, headers=h)
    assert u.status_code == 200
    body = u.json()
    assert body["phone_masked"] == rows[0]["phone_masked"] and "phone_e164" not in body
    assert body["verified"] is False and body["disabled"] is False and body["roles"]
    assert (await client.get(f"{BASE}/users", params={"phone": "07 55 55 55 55"}, headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/users", params={"phone": "abc"}, headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_send_returns_a_whatsapp_link_and_logs_it(client):
    h = await _admin(client)
    await make_user(SHOPPER, verified=False)
    cid = await _open(SHOPPER_E164, "verify_number")
    r = await client.post(f"{BASE}/checks/{cid}/send", headers=h)
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://wa.me/")
    acts = await _actions()
    assert [a.action for a in acts] == ["send_check"]
    assert acts[0].check_id == cid and acts[0].user_id == await _user_id(SHOPPER_E164)
    assert acts[0].admin_user_id == await _user_id("+2250799000001") and acts[0].ip
    # a sent check can be sent again; a refused one cannot
    assert (await client.post(f"{BASE}/checks/{cid}/send", headers=h)).status_code == 200
    assert (await client.post(f"{BASE}/checks/{cid}/refuse", headers=h)).status_code == 204
    again = await client.post(f"{BASE}/checks/{cid}/send", headers=h)
    assert again.status_code == 409 and again.json()["detail"] == "Cette demande est deja traitee."
    assert (await client.post(f"{BASE}/checks/{cid}/refuse", headers=h)).status_code == 409
    assert (await client.post(f"{BASE}/checks/9999/send", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_refused_number_is_shown_to_the_user(client):
    h = await _admin(client)
    await make_user(SHOPPER, verified=False)
    mine = await _h(client, SHOPPER, "customer")
    before = (await client.get("/api/auth/me", headers=mine)).json()
    assert before["verified"] is False and before["number_refused"] is False
    cid = await _open(SHOPPER_E164, "verify_number")
    assert (await client.post(f"{BASE}/checks/{cid}/refuse", headers=h)).status_code == 204
    after = (await client.get("/api/auth/me", headers=mine)).json()
    assert after["verified"] is False and after["number_refused"] is True
    assert "refuse_check" in [a.action for a in await _actions()]


@pytest.mark.asyncio
async def test_suspend_and_sign_out(client):
    h = await _admin(client)
    await make_user(SHOPPER)
    mine = await _h(client, SHOPPER, "customer")
    uid = await _user_id(SHOPPER_E164)
    assert (await client.post(f"{BASE}/users/{uid}/sign-out", headers=h)).status_code == 204
    async with AsyncSessionLocal() as db:
        live = (await db.execute(select(models.RefreshToken).where(models.RefreshToken.user_id == uid, models.RefreshToken.revoked_at.is_(None)))).scalars().all()
    assert live == []
    assert (await client.post(f"{BASE}/users/{uid}/suspend", headers=h)).status_code == 204
    assert (await sign_in(client, SHOPPER)).status_code != 200
    assert (await client.get(f"{BASE}/users", params={"phone": SHOPPER}, headers=h)).json()["disabled"] is True
    assert (await client.post(f"{BASE}/users/{uid}/restore", headers=h)).status_code == 204
    assert (await sign_in(client, SHOPPER)).status_code == 200
    assert (await client.post(f"{BASE}/users/9999/suspend", headers=h)).status_code == 404
    names = [a.action for a in await _actions()]
    assert names == ["sign_out", "suspend", "find_user", "restore"]
    assert mine


@pytest.mark.asyncio
async def test_reset_password_opens_a_check(client):
    h = await _admin(client)
    await make_user(SHOPPER)
    uid = await _user_id(SHOPPER_E164)
    r = await client.post(f"{BASE}/users/{uid}/reset-password", headers=h)
    assert r.status_code == 200
    cid = r.json()["check_id"]
    async with AsyncSessionLocal() as db:
        check = await db.get(models.AccountCheck, cid)
        user = await db.get(models.User, uid)
    assert check.kind == "reset_password" and check.status == "pending" and check.team_created is False
    assert user.must_change_password is False and user.password_hash
    assert (await sign_in(client, SHOPPER)).status_code == 200
    assert [a.action for a in await _actions()] == ["reset_password"]
    assert (await client.post(f"{BASE}/users/9999/reset-password", headers=h)).status_code == 404


# --- Shared test logins ---------------------------------------------------------

TESTER = "07 00 00 00 01"
SUPER = "07 99 00 00 03"


async def _super(ac):
    await make_user(SUPER, roles="admin,superadmin")
    return await _h(ac, SUPER, "admin")


@pytest.mark.asyncio
async def test_the_super_admin_sets_one_password_for_every_test_login(client):
    h = await _super(client)
    listed = await client.get(f"{BASE}/test-accounts", headers=h)
    assert listed.status_code == 200
    assert {a["role"] for a in listed.json()} == {"customer", "merchant", "cashier", "agent", "admin"}

    r = await client.put(f"{BASE}/test-accounts/password", json={"password": OTHER_PASSWORD}, headers=h)
    assert r.status_code == 204, r.text
    assert (await sign_in(client, TESTER, password=OTHER_PASSWORD)).status_code == 200
    assert (await sign_in(client, "07 00 00 00 02", "merchant", password=OTHER_PASSWORD)).status_code == 200
    assert all(a["has_password"] for a in (await client.get(f"{BASE}/test-accounts", headers=h)).json())
    # The super admin who did it keeps their own password.
    assert (await sign_in(client, SUPER, "admin")).status_code == 200


@pytest.mark.asyncio
async def test_a_weak_test_password_is_refused(client):
    h = await _super(client)
    r = await client.put(f"{BASE}/test-accounts/password", json={"password": "12345678"}, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_test_logins_cannot_be_touched_in_production(client, monkeypatch):
    h = await _super(client)
    monkeypatch.setenv("FIDELIA_ENV", "production")
    assert (await client.get(f"{BASE}/test-accounts", headers=h)).status_code == 404
    assert (await client.put(f"{BASE}/test-accounts/password", json={"password": OTHER_PASSWORD}, headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_only_the_super_admin_sees_and_sets_the_test_password(client):
    await make_user(AGENT, roles="agent")
    for h in (await _admin(client), await _h(client, AGENT, "admin")):
        assert (await client.get(f"{BASE}/test-accounts", headers=h)).status_code == 403
        r = await client.put(f"{BASE}/test-accounts/password", json={"password": OTHER_PASSWORD}, headers=h)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_an_admin_cannot_lock_the_super_admin_out(client):
    await _super(client)
    h = await _admin(client)
    target = await _user_id("+2250799000003")
    for action in ("suspend", "sign-out", "reset-password"):
        assert (await client.post(f"{BASE}/users/{target}/{action}", headers=h)).status_code == 403
    assert (await sign_in(client, SUPER, "admin")).status_code == 200


# --- Removing accounts and shops -----------------------------------------------


@pytest.mark.asyncio
async def test_an_admin_deletes_a_customer_even_after_looking_them_up_and_checking_them(client):
    h = await _admin(client)
    await make_user(SHOPPER)
    await _open(SHOPPER_E164, "verify_number")
    found = await client.get(f"{BASE}/users", params={"phone": SHOPPER}, headers=h)
    user_id = found.json()["id"]
    r = await client.delete(f"{BASE}/users/{user_id}", headers=h)
    assert r.status_code == 204, r.text
    assert (await client.get(f"{BASE}/users", params={"phone": SHOPPER}, headers=h)).status_code == 404
    assert (await sign_in(client, SHOPPER)).status_code == 401


@pytest.mark.asyncio
async def test_an_admin_cannot_delete_a_shop_owner_themselves_or_the_super_admin(client):
    h = await _admin(client)
    await _super(client)
    await make_user(OWNER, roles="merchant")
    async with AsyncSessionLocal() as db:
        db.add(models.Venue(category="maquis", name="Chez Test", commune="Cocody", owner_username="tel:+2250712345679"))
        await db.commit()
    owner = await _user_id("+2250712345679")
    assert (await client.delete(f"{BASE}/users/{owner}", headers=h)).status_code == 409
    assert (await client.delete(f"{BASE}/users/{await _user_id('+2250799000001')}", headers=h)).status_code == 409
    assert (await client.delete(f"{BASE}/users/{await _user_id('+2250799000003')}", headers=h)).status_code == 403


async def _shop_with_everything(ac):
    """A shop with an owner, a cashier, a deal, a reward and a customer's payment."""
    from datetime import datetime, timedelta

    await make_user(OWNER, roles="merchant")
    await make_user(NEWBIE, roles="cashier")
    await make_user(SHOPPER)
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        venue = models.Venue(category="maquis", name="Chez Test", commune="Cocody", owner_username="tel:+2250712345679", is_sample=True)
        venue.rewards = [models.LoyaltyReward(title="Boisson", cost_points=10)]
        db.add(venue)
        await db.flush()
        db.add(models.VenueStaff(venue_id=venue.id, user_key="tel:+2250712345680", name="Caissier", added_by="tel:+2250712345679", created_at=now))
        db.add(models.Deal(venue_id=venue.id, title="Promo", starts_at=now, ends_at=now + timedelta(days=3), active=True, created_at=now))
        await db.commit()
        return venue.id


@pytest.mark.asyncio
async def test_the_super_admin_removes_a_shop_with_its_data_and_the_logins_only_it_needed(client):
    h = await _super(client)
    venue_id = await _shop_with_everything(client)
    listed = await client.get(f"{BASE}/shops", params={"q": "chez"}, headers=h)
    assert [s["name"] for s in listed.json()] == ["Chez Test"]

    refused = await client.request("DELETE", f"{BASE}/shops/{venue_id}", json={"confirm_name": "Chez"}, headers=h)
    assert refused.status_code == 422
    r = await client.request("DELETE", f"{BASE}/shops/{venue_id}", json={"confirm_name": "Chez Test"}, headers=h)
    assert r.status_code == 200, r.text
    deleted = r.json()["deleted"]
    assert deleted["venues"] == 1 and deleted["deals"] == 1 and deleted["loyalty_rewards"] == 1 and deleted["venue_staff"] == 1
    assert deleted["users"] == 2
    async with AsyncSessionLocal() as db:
        assert await db.get(models.Venue, venue_id) is None
        left = (await db.execute(select(models.User.phone_e164))).scalars().all()
    assert "+2250712345679" not in left and "+2250712345680" not in left
    # A customer who only shopped there keeps their account.
    assert SHOPPER_E164 in left


@pytest.mark.asyncio
async def test_only_the_super_admin_lists_and_removes_shops(client):
    h = await _admin(client)
    venue_id = await _shop_with_everything(client)
    assert (await client.get(f"{BASE}/shops", headers=h)).status_code == 403
    r = await client.request("DELETE", f"{BASE}/shops/{venue_id}", json={"confirm_name": "Chez Test"}, headers=h)
    assert r.status_code == 403
