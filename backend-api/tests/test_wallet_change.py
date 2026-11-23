"""Smoke tests for the wallet-change process (merchant request -> admin WhatsApp code -> confirmation -> 24 h -> active, "this wasn't
me", admin call-and-activate, first-week cap). Auth tokens are signed with a local key, as in test_sso.py. No e2e."""

import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select, update

from app import models
from app.core import sso
from app.core.security import create_access_token
from app.db import AsyncSessionLocal
from app.services import admin_alerts, wallet_change
from tests.test_sso import PHONE, bearer, client, sso_on, token  # noqa: F401  (client and sso_on are fixtures)

ADMIN_PHONE = "+2250700000001"
WALLET_A = "+2250701111111"
WALLET_B = "+2250702222222"


@pytest.fixture(autouse=True)
def _alive_and_alerts(monkeypatch, client, sso_on):  # `client` first: it clears the SSO env, `sso_on` sets it back
    async def alive(_t):
        return True

    monkeypatch.setattr(sso, "session_alive", alive)
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("NTFY_URL", "memory")
    admin_alerts.SENT.clear()


def merchant(**over) -> dict:
    return bearer(token(role="merchant", roles=["merchant"], app="merchant", **over))


def admin(sub="a1", amr=("pwd", "totp"), phone=ADMIN_PHONE, **over) -> dict:
    return bearer(token(role="admin", roles=["admin"], app="admin", ph=f"tel:{phone}", sub=sub, amr=list(amr), **over))


async def admin_legacy(client):
    return bearer((await client.post("/api/token", data={"username": "admin", "password": "admin123"})).json()["access_token"])


async def enrol(client, wallet=None, name="Maquis Wallet"):
    shop = {"category": "maquis", "name": name, "commune": "Treichville", "merchant_phone": PHONE}
    if wallet:
        shop |= {"payout_provider": "wave", "payout_account": wallet}
    r = await client.post("/api/admin/venues", json=shop, headers=await admin_legacy(client))
    assert r.status_code == 201, r.text
    return r.json()


async def request(client, account=WALLET_B, provider="wave", h=None):
    return await client.post("/api/merchant/wallet-change", json={"provider": provider, "account": account}, headers=h or merchant())


async def send_code(client, change_id, h=None) -> tuple[str, str]:
    r = await client.post(f"/api/admin/wallet-changes/{change_id}/send-code", headers=h or admin())
    assert r.status_code == 200, r.text
    text = parse_qs(urlsplit(r.json()["url"]).query)["text"][0]
    return r.json()["url"], text.split("*")[1]


async def venue_row(venue_id):
    async with AsyncSessionLocal() as db:
        return await db.get(models.Venue, venue_id)


async def set_change(change_id, **values):
    async with AsyncSessionLocal() as db:
        await db.execute(update(models.WalletChange).where(models.WalletChange.id == change_id).values(**values))
        await db.commit()


# --- the whole story -----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_of_an_existing_wallet_waits_for_the_code_and_for_24_hours(client):
    v = await enrol(client, wallet=WALLET_A)
    r = await request(client)
    assert r.status_code == 201 and r.json()["status"] == "pending_confirmation" and r.json()["account_masked"].endswith("2222")
    assert (await venue_row(v["id"])).payout_account == WALLET_A  # nothing changes yet
    cid = r.json()["id"]

    listed = (await client.get("/api/admin/wallet-changes", headers=admin())).json()
    assert len(listed) == 1 and listed[0]["shop"] == "Maquis Wallet" and listed[0]["current_account_masked"].endswith("1111") and listed[0]["merchant_phone_masked"]
    assert WALLET_B not in str(listed) and "events" in listed[0]

    url, code = await send_code(client, cid)
    assert url.startswith("https://wa.me/2250701020304?text=")  # the merchant's LOGIN number, not the wallet
    assert "Maquis Wallet" in parse_qs(urlsplit(url).query)["text"][0] and "2222" in parse_qs(urlsplit(url).query)["text"][0] and WALLET_B not in url

    bad = "000000" if code != "000000" else "111111"
    assert (await client.post("/api/merchant/wallet-change/confirm", json={"code": bad}, headers=merchant())).json()["detail"] == "wrong_code"
    ok = await client.post("/api/merchant/wallet-change/confirm", json={"code": code}, headers=merchant())
    assert ok.status_code == 200 and ok.json()["status"] == "confirmed_waiting"
    wait = datetime.fromisoformat(ok.json()["activates_at"]) - datetime.utcnow()
    assert timedelta(hours=23, minutes=55) < wait <= timedelta(hours=24)
    assert (await venue_row(v["id"])).payout_account == WALLET_A  # still the old wallet during the delay

    await set_change(cid, activates_at=datetime.utcnow() - timedelta(minutes=1))  # the 24 h are over
    state = (await client.get("/api/merchant/wallet", headers=merchant())).json()
    row = await venue_row(v["id"])
    assert row.payout_account == WALLET_B and state["account_masked"].endswith("2222") and state["change"]["status"] == "active"
    assert row.wallet_active_since is not None and state["cap_xof"] == 50000


@pytest.mark.asyncio
async def test_a_first_wallet_needs_the_code_but_no_delay_and_gets_the_payment_qr(client):
    v = await enrol(client)  # enrolled by an admin without a wallet
    assert v["pay_code"] is None
    r = await request(client, account=WALLET_A)
    _url, code = await send_code(client, r.json()["id"])
    done = await client.post("/api/merchant/wallet-change/confirm", json={"code": code}, headers=merchant())
    assert done.json()["status"] == "active" and done.json()["activation_mode"] == "first_wallet"
    row = await venue_row(v["id"])
    assert row.payout_account == WALLET_A and row.pay_code and row.wallet_active_since


# --- who may do what --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_request_needs_an_auth_sign_in_with_a_recent_password(client):
    await enrol(client, wallet=WALLET_A)
    legacy = bearer(create_access_token({"sub": f"tel:{PHONE}", "role": "merchant"}))
    assert (await request(client, h=legacy)).json()["detail"] == "auth_login_required"
    stale = merchant(auth_time=int(time.time()) - 3600)
    assert (await request(client, h=stale)).json()["detail"] == "step_up_required"
    cashier = bearer(token(role="cashier", roles=["cashier"], app="merchant"))
    assert (await request(client, h=cashier)).status_code == 403
    assert (await request(client, account="abc", h=merchant())).status_code == 422
    assert (await request(client, provider="paypal")).status_code == 422
    assert (await request(client, account=WALLET_A)).json()["detail"] == "same_wallet"
    assert (await request(client)).status_code == 201
    assert (await request(client, account="0703333333")).json()["detail"] == "change_in_progress"


@pytest.mark.asyncio
async def test_admin_routes_need_an_admin_with_the_authenticator_code(client):
    await enrol(client, wallet=WALLET_A)
    cid = (await request(client)).json()["id"]
    no_totp = admin(amr=("pwd",))
    for method, path in (("get", "/api/admin/wallet-changes"), ("post", f"/api/admin/wallet-changes/{cid}/send-code")):
        r = await getattr(client, method)(path, headers=no_totp)
        assert r.status_code == 403 and r.json()["detail"] == "step_up_required"
    assert (await client.get("/api/admin/wallet-changes", headers=merchant())).status_code == 403
    assert (await client.get("/api/admin/wallet-changes", headers=bearer(token()))).status_code == 403
    assert (await client.get("/api/admin/wallet-changes", headers=await admin_legacy(client))).json()["detail"] == "auth_login_required"


# --- the code -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_code_rules_expiry_attempts_and_resend(client):
    await enrol(client, wallet=WALLET_A)
    cid = (await request(client)).json()["id"]
    confirm = lambda c: client.post("/api/merchant/wallet-change/confirm", json={"code": c}, headers=merchant())  # noqa: E731
    assert (await confirm("123456")).json()["detail"] == "no_code"  # nothing sent yet
    _u, old = await send_code(client, cid)
    _u, new = await send_code(client, cid)  # a new code voids the old one
    if old != new:
        assert (await confirm(old)).json()["detail"] == "wrong_code"
    bad = "000000" if new != "000000" else "111111"
    for _ in range(4):
        await confirm(bad)
    assert (await confirm(new)).status_code == 429  # five wrong guesses: locked, even for the right code
    _u, fresh = await send_code(client, cid)  # an admin sends a new one
    await set_change(cid, code_expires_at=datetime.utcnow() - timedelta(minutes=1))
    assert (await confirm(fresh)).json()["detail"] == "no_code"  # expired


# --- "this wasn't me" -----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_this_wasnt_me_freezes_the_change_and_alerts_the_admins(client):
    v = await enrol(client, wallet=WALLET_A, name="Maquis Alerte")
    cid = (await request(client)).json()["id"]
    _u, code = await send_code(client, cid)
    legacy = bearer(create_access_token({"sub": f"tel:{PHONE}", "role": "merchant"}))  # even a legacy session may press it
    r = await client.post("/api/merchant/wallet-change/not-me", headers=legacy)
    assert r.status_code == 200 and r.json()["status"] == "frozen"
    assert any("Maquis Alerte" in a["message"] and a["priority"] == 5 for a in admin_alerts.SENT)
    frozen_confirm = await client.post("/api/merchant/wallet-change/confirm", json={"code": code}, headers=merchant())
    assert frozen_confirm.status_code == 409 and frozen_confirm.json()["detail"] == "not_awaiting_code"  # frozen: the code no longer works
    assert (await request(client, account="0703333333")).json()["detail"] == "frozen_review"
    fast = await client.post(f"/api/admin/wallet-changes/{cid}/activate-now", json={"call_note": "called the owner, voice matched"}, headers=admin())
    assert fast.status_code == 409 and fast.json()["detail"] == "frozen_review"  # the fast path cannot override "not me"
    assert (await client.post(f"/api/admin/wallet-changes/{cid}/reject", json={"reason": "owner says not him"}, headers=admin())).json()["status"] == "rejected"
    assert (await venue_row(v["id"])).payout_account == WALLET_A
    assert (await request(client, account="0703333333")).status_code == 201  # after the review a new request is possible


# --- admin fast path ------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_call_and_activate_needs_a_note_is_audited_and_alerts_at_three_a_day(client):
    v = await enrol(client, wallet=WALLET_A)
    cid = (await request(client)).json()["id"]
    assert (await client.post(f"/api/admin/wallet-changes/{cid}/activate-now", json={"call_note": "ok"}, headers=admin())).json()["detail"] == "call_note_required"
    r = await client.post(f"/api/admin/wallet-changes/{cid}/activate-now", json={"call_note": "Called +225 07 ... : owner confirmed, knows the new number"}, headers=admin())
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["activation_mode"] == "admin_call"
    assert (await venue_row(v["id"])).payout_account == WALLET_B
    trail = (await client.get("/api/admin/wallet-changes?status=all", headers=admin())).json()[0]
    assert "owner confirmed" in trail["call_note"] and [e["action"] for e in trail["events"]] == ["requested", "activated_admin_call"]
    assert not admin_alerts.SENT  # one is normal

    # the same admin activating a 2nd and a 3rd the same day raises an alert; another admin's count is separate
    for i in range(2):
        other = await enrol(client, wallet=WALLET_A, name=f"Shop {i}") if False else None  # (one merchant number = one shop: reuse the same shop)
        nxt = await request(client, account=f"07044444{i}{i}")
        assert nxt.status_code == 201, nxt.text
        await client.post(f"/api/admin/wallet-changes/{nxt.json()['id']}/activate-now", json={"call_note": "called, confirmed again"}, headers=admin())
    assert any("par appel" in a["title"] for a in admin_alerts.SENT)


@pytest.mark.asyncio
async def test_the_trail_never_holds_codes_or_full_numbers(client):
    await enrol(client, wallet=WALLET_A)
    cid = (await request(client)).json()["id"]
    _u, code = await send_code(client, cid)
    await client.post("/api/merchant/wallet-change/confirm", json={"code": code}, headers=merchant())
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(models.WalletChangeEvent))).scalars().all()
    dump = str([(e.actor, e.action, e.detail) for e in events])
    assert code not in dump and WALLET_B not in dump and "2222" in dump  # masked only
    listed = (await client.get("/api/admin/wallet-changes?status=all", headers=admin())).json()
    assert code not in str(listed) and WALLET_B not in str(listed)


# --- the first-week cap -------------------------------------------------------------------------------------------------------------


async def pay(client, pay_code, amount):
    cust = bearer(create_access_token({"sub": "tel:+2250709090909", "role": "customer"}))
    return await client.post("/api/customer/payments", headers=cust, json={
        "pay_code": pay_code, "amount": amount, "wallet_provider": "wave", "payer_msisdn": "+2250712345678", "idempotency_key": uuid.uuid4().hex})


@pytest.mark.asyncio
async def test_a_new_wallet_is_capped_for_its_first_week_even_after_an_immediate_activation(client):
    v = await enrol(client, wallet=WALLET_A)
    pay_code = v["pay_code"]
    assert (await pay(client, pay_code, 60000)).status_code == 201  # an existing wallet from before the process: no cap (grandfathered)
    cid = (await request(client)).json()["id"]
    await client.post(f"/api/admin/wallet-changes/{cid}/activate-now", json={"call_note": "called, confirmed by voice"}, headers=admin())
    assert (await pay(client, pay_code, 30000)).status_code == 201
    over = await pay(client, pay_code, 25000)
    assert over.status_code == 409 and over.json()["detail"] == "wallet_cap_reached"
    assert (await pay(client, pay_code, 20000)).status_code == 201  # exactly 50,000 in total is allowed
    assert (await pay(client, pay_code, 100)).json()["detail"] == "wallet_cap_reached"  # 100 XOF is the minimum payment
    # after the first week the cap is gone
    async with AsyncSessionLocal() as db:
        await db.execute(update(models.Venue).where(models.Venue.id == v["id"]).values(wallet_active_since=datetime.utcnow() - timedelta(days=8)))
        await db.commit()
    assert (await pay(client, pay_code, 40000)).status_code == 201


@pytest.mark.asyncio
async def test_the_delay_and_cap_are_settings(client, monkeypatch):
    monkeypatch.setenv("WALLET_CHANGE_DELAY_HOURS", "1")
    monkeypatch.setenv("WALLET_NEW_CAP_XOF", "1000")
    await enrol(client, wallet=WALLET_A)
    cid = (await request(client)).json()["id"]
    _u, code = await send_code(client, cid)
    done = (await client.post("/api/merchant/wallet-change/confirm", json={"code": code}, headers=merchant())).json()
    assert timedelta(minutes=55) < datetime.fromisoformat(done["activates_at"]) - datetime.utcnow() <= timedelta(hours=1)
    assert wallet_change.cap_xof() == 1000
