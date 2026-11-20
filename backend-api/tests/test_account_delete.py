"""Deleting an account (Google Play's account deletion requirement).

A customer deletes their own account at once: what identifies them is erased,
what is also the merchants' record stays under a key that names nobody, so a
shop's history and totals do not change. Merchants and cashiers ask; an admin
deletes once the person owns no shop.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from datetime import datetime

from sqlalchemy import func, select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from app.services import account_delete

PHONE = "07 12 34 56 78"
E164 = "+2250712345678"
KEY = "tel:" + E164


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


async def _age_codes():
    from datetime import timedelta

    async with AsyncSessionLocal() as db:
        for c in (await db.execute(select(models.OtpChallenge))).scalars():
            c.created_at -= timedelta(seconds=400)
        await db.commit()


async def _sign_in(ac, phone=PHONE, app_name="customer"):
    await _age_codes()
    code = (await ac.post("/api/auth/otp/request", json={"phone": phone, "app": app_name})).json()["dev_code"]
    r = await ac.post("/api/auth/otp/verify", json={"phone": phone, "code": code, "app": app_name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _password(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _count(model, *where):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def _earn_and_pay(ac, customer):
    """Points from a counter sale, and a Wave payment from the app."""
    merchant = await _password(ac, "demo", "demo123")
    sale = await ac.post(
        "/api/merchant/sales",
        json={"amount": "5000", "idempotency_key": "del-sale-0001", "customer_phone": PHONE, "customer_consent": True},
        headers=merchant,
    )
    assert sale.status_code == 201, sale.text
    req = (await ac.post("/api/merchant/payment-requests", json={"amount": 2000}, headers=merchant)).json()
    paid = await ac.post(
        "/api/customer/payments",
        json={"pay_code": req["code"], "wallet_provider": "wave", "payer_msisdn": E164, "idempotency_key": "del-pay-0001"},
        headers=customer,
    )
    assert paid.status_code == 201, paid.text


def test_every_column_that_names_a_person_is_classified():
    assert account_delete.unclassified() == []


@pytest.mark.asyncio
async def test_a_customer_deletes_their_account_and_the_shop_keeps_its_figures(client):
    customer = await _sign_in(client)
    await _earn_and_pay(client, customer)
    sales_before = await _count(models.SaleEvent)
    assert await _count(models.LoyaltyEntry, models.LoyaltyEntry.customer_id == KEY) > 0

    r = await client.delete("/api/account", headers=customer)
    assert r.status_code == 200, r.text

    # The person is gone...
    assert await _count(models.User, models.User.phone_e164 == E164) == 0
    assert await _count(models.LoyaltyEntry, models.LoyaltyEntry.customer_id == KEY) == 0
    assert await _count(models.LoyaltyConsent, models.LoyaltyConsent.customer_id == KEY) == 0
    assert await _count(models.SaleEvent, models.SaleEvent.customer_id == KEY) == 0
    assert await _count(models.CustomerPayment, models.CustomerPayment.customer_id == KEY) == 0
    assert await _count(models.CustomerPayment, models.CustomerPayment.payer_msisdn == E164) == 0
    assert await _count(models.OtpChallenge, models.OtpChallenge.phone_e164 == E164) == 0
    # ...the shop's records are not.
    assert await _count(models.SaleEvent) == sales_before
    assert await _count(models.CustomerPayment, models.CustomerPayment.customer_id.like("deleted:%")) == 1

    # Signing in again opens a new, empty account.
    again = await _sign_in(client)
    assert (await client.get("/api/customer/loyalty", headers=again)).json()["total_points"] == 0


@pytest.mark.asyncio
async def test_a_shop_number_is_sent_to_the_team(client):
    # The seeded merchant's number, signed in to the customer app.
    as_customer = await _sign_in(client, "07 00 00 00 02")
    r = await client.delete("/api/account", headers=as_customer)
    assert r.status_code == 409
    assert "Fidelia Pro" in r.json()["detail"]
    merchant = await _sign_in(client, "07 00 00 00 02", "merchant")
    assert (await client.delete("/api/account", headers=merchant)).status_code == 403


@pytest.mark.asyncio
async def test_an_unfinished_layaway_blocks_deletion(client):
    customer = await _sign_in(client)
    async with AsyncSessionLocal() as db:
        venue = (await db.execute(select(models.Venue))).scalars().first()
        from datetime import datetime

        db.add(models.LayawayPlan(
            venue_id=venue.id, customer_id=KEY, item="Radio", price=10000, currency="XOF", status="open",
            due_by=datetime(2027, 1, 1), terms_version="v", created_by="demo", created_at=datetime(2026, 10, 1),
        ))
        await db.commit()
    r = await client.delete("/api/account", headers=customer)
    assert r.status_code == 409
    assert "plusieurs fois" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_cashier_asks_and_an_admin_deletes(client):
    cashier = await _sign_in(client, "07 00 00 00 03", "merchant")
    first = await client.post("/api/account/deletion-request", json={"reason": "Je quitte le commerce"}, headers=cashier)
    again = await client.post("/api/account/deletion-request", json={}, headers=cashier)
    assert first.status_code == again.status_code == 202
    assert first.json()["id"] == again.json()["id"]

    admin = await _sign_in(client, "07 00 00 00 09", "admin")
    pending = (await client.get("/api/admin/deletion-requests", headers=admin)).json()
    assert [(p["phone"], p["role"], p["reason"]) for p in pending] == [("+2250700000003", "cashier", "Je quitte le commerce")]
    assert pending[0]["venue_name"]

    done = await client.post(f"/api/admin/deletion-requests/{pending[0]['id']}/done", json={"note": "ok"}, headers=admin)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"
    assert await _count(models.User, models.User.phone_e164 == "+2250700000003") == 0
    cashier_key = "tel:+2250700000003"
    assert await _count(models.VenueStaff, models.VenueStaff.user_key == cashier_key) == 0
    assert await _count(models.SaleEvent, models.SaleEvent.recorded_by == cashier_key) == 0


@pytest.mark.asyncio
async def test_an_owner_is_deleted_only_once_the_shop_is_handed_over(client):
    owner = await _sign_in(client, "07 00 00 00 02", "merchant")
    assert (await client.post("/api/account/deletion-request", json={}, headers=owner)).status_code == 202
    admin = await _sign_in(client, "07 00 00 00 09", "admin")
    request = (await client.get("/api/admin/deletion-requests", headers=admin)).json()[0]
    r = await client.post(f"/api/admin/deletion-requests/{request['id']}/done", json={}, headers=admin)
    assert r.status_code == 409
    assert "commerce" in r.json()["detail"]
    assert await _count(models.User, models.User.phone_e164 == "+2250700000002") == 1

    rejected = await client.post(f"/api/admin/deletion-requests/{request['id']}/reject", json={"note": "doublon"}, headers=admin)
    assert rejected.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_only_admins_see_and_decide_requests(client):
    customer = await _sign_in(client)
    assert (await client.get("/api/admin/deletion-requests", headers=customer)).status_code == 403


# --- auth is told (platform SSO): the identity there goes after the data here ---------------------------------------------


@pytest.fixture
def told_auth(monkeypatch):
    from app.core import sso

    calls: list[str] = []

    async def fake(phone):
        calls.append(phone)
        return True

    monkeypatch.setattr(sso, "erase_identity", fake)
    return calls


@pytest.mark.asyncio
async def test_a_customer_deleting_her_account_tells_auth_afterwards(client, told_auth):
    customer = await _sign_in(client)
    assert (await client.delete("/api/account", headers=customer)).status_code == 200
    assert told_auth == [E164]


@pytest.mark.asyncio
async def test_a_refused_deletion_does_not_touch_auth(client, told_auth):
    as_customer = await _sign_in(client, "07 00 00 00 02")  # a shop's number
    assert (await client.delete("/api/account", headers=as_customer)).status_code == 409
    assert told_auth == []


@pytest.mark.asyncio
async def test_an_admin_closing_a_deletion_request_tells_auth(client, told_auth):
    cashier = await _sign_in(client, "07 00 00 00 03", "merchant")
    await client.post("/api/account/deletion-request", json={}, headers=cashier)
    admin = await _sign_in(client, "07 00 00 00 09", "admin")
    pending = (await client.get("/api/admin/deletion-requests", headers=admin)).json()
    assert (await client.post(f"/api/admin/deletion-requests/{pending[0]['id']}/done", json={"note": "ok"}, headers=admin)).status_code == 200
    assert told_auth == ["+2250700000003"]


@pytest.mark.asyncio
async def test_rejecting_a_request_does_not_touch_auth(client, told_auth):
    cashier = await _sign_in(client, "07 00 00 00 03", "merchant")
    await client.post("/api/account/deletion-request", json={}, headers=cashier)
    admin = await _sign_in(client, "07 00 00 00 09", "admin")
    pending = (await client.get("/api/admin/deletion-requests", headers=admin)).json()
    await client.post(f"/api/admin/deletion-requests/{pending[0]['id']}/reject", json={"note": "doublon"}, headers=admin)
    assert told_auth == []


@pytest.mark.asyncio
async def test_erase_identity_calls_auth_with_the_service_key_and_never_raises(monkeypatch, caplog):
    import httpx

    from app.core import sso

    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("x-service-key"), request.content))
        return httpx.Response(200, json={"result": "erased"})

    real = httpx.AsyncClient
    monkeypatch.setattr(sso.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert await sso.erase_identity(E164) is None  # SSO off: nothing is sent, nothing to retry
    monkeypatch.setenv("FIDELIA_SSO_ENABLED", "1")
    monkeypatch.setenv("FIDELIA_SSO_ISSUER", "http://auth.test")
    monkeypatch.setenv("FIDELIA_SSO_JWKS_URL", "http://auth.test/.well-known/jwks.json")
    monkeypatch.setenv("FIDELIA_SSO_AUTH_URL", "http://auth.test/")
    monkeypatch.delenv("FIDELIA_SSO_SERVICE_KEY", raising=False)
    assert await sso.erase_identity(E164) is None  # no service key: nothing is sent
    monkeypatch.setenv("FIDELIA_SSO_SERVICE_KEY", "svc-key")
    assert await sso.erase_identity(E164) is True
    assert seen == [("http://auth.test/v1/service/erase", "svc-key", b'{"phone":"%s"}' % E164.encode())]

    def down(request):
        raise httpx.ConnectError("auth is down")

    monkeypatch.setattr(sso.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(down), **kw))
    caplog.set_level("ERROR")
    assert await sso.erase_identity(E164) is False
    assert "FAILED" in caplog.text and E164 not in caplog.text  # logged for a rerun, without the number


# --- the auth service moves a number: fidelia moves its data first ---------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_phone_hook_moves_the_account_and_is_idempotent(client, monkeypatch):
    monkeypatch.setenv("FIDELIA_AUTH_HOOK_KEY", "k" * 32)
    await _sign_in(client)
    key = {"X-Service-Key": "k" * 32}
    body = {"old_phone": E164, "new_phone": "+2250755555555"}
    r = await client.post("/api/internal/phone-changed", json=body, headers=key)
    assert r.status_code == 200 and r.json() == {"ok": True, "moved": True}
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(models.User).where(models.User.phone_e164 == "+2250755555555"))).scalar_one_or_none() is not None
        assert (await db.execute(select(models.AccountNumberChange.method))).scalars().all() == ["auth"]
    again = await client.post("/api/internal/phone-changed", json=body, headers=key)
    assert again.json() == {"ok": True, "moved": False}


@pytest.mark.asyncio
async def test_auth_phone_hook_needs_the_key_and_refuses_a_taken_number(client, monkeypatch):
    body = {"old_phone": E164, "new_phone": "+2250755555555"}
    assert (await client.post("/api/internal/phone-changed", json=body, headers={"X-Service-Key": "k" * 32})).status_code == 403  # off: no key set
    monkeypatch.setenv("FIDELIA_AUTH_HOOK_KEY", "k" * 32)
    assert (await client.post("/api/internal/phone-changed", json=body)).status_code == 403
    assert (await client.post("/api/internal/phone-changed", json=body, headers={"X-Service-Key": "x" * 32})).status_code == 403
    await _sign_in(client)
    await _sign_in(client, "07 55 55 55 55")
    taken = await client.post("/api/internal/phone-changed", json=body, headers={"X-Service-Key": "k" * 32})
    assert taken.status_code == 409


def test_the_hook_is_reachable_without_the_cloudflare_header_but_nothing_else_is():
    from app import edge

    assert "/api/internal/phone-changed" in edge.EXEMPT_PATHS
    assert "/api/account" not in edge.EXEMPT_PATHS


# --- auth is down when someone is deleted: the call is queued and retried -------------------------------------------------


@pytest.fixture
def auth_state(monkeypatch):
    """`state["answer"]`: True = auth answers, False = unreachable, None = SSO not configured. `state["calls"]` records the numbers sent."""
    from app.core import sso

    state = {"answer": False, "calls": []}

    async def fake(phone):
        state["calls"].append(phone)
        return state["answer"]

    monkeypatch.setattr(sso, "erase_identity", fake)
    return state


async def _outbox():
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(models.AuthEraseOutbox).order_by(models.AuthEraseOutbox.id))).scalars())


@pytest.mark.asyncio
async def test_a_deletion_while_auth_is_down_is_queued_with_the_number_sealed(client, auth_state):
    from app.core import secretbox

    customer = await _sign_in(client)
    assert (await client.delete("/api/account", headers=customer)).status_code == 200  # the deletion stands
    rows = await _outbox()
    assert len(rows) == 1 and rows[0].status == "pending" and rows[0].attempts == 1
    assert E164 not in rows[0].phone_sealed and secretbox.unseal(rows[0].phone_sealed) == E164  # sealed at rest


@pytest.mark.asyncio
async def test_nothing_is_queued_when_auth_answers_or_is_not_configured(client, auth_state):
    from app.services import auth_erase

    auth_state["answer"] = True
    await auth_erase.tell_auth(E164)
    auth_state["answer"] = None
    await auth_erase.tell_auth(E164)
    assert await _outbox() == []


@pytest.mark.asyncio
async def test_the_job_retries_with_a_growing_delay_then_finishes_and_forgets_the_number(client, auth_state):
    from datetime import datetime, timedelta

    from app.services import auth_erase

    await auth_erase.tell_auth(E164)
    row = (await _outbox())[0]
    soon = row.created_at + timedelta(minutes=2)
    assert await auth_erase.process_outbox(row.created_at) == {"done": 0, "retry": 0, "gave_up": 0, "purged": 0}  # not due yet
    out = await auth_erase.process_outbox(soon)  # still down
    assert out["retry"] == 1
    row = (await _outbox())[0]
    assert row.attempts == 2 and row.next_attempt_at - soon == timedelta(minutes=2)
    auth_state["answer"] = True
    later = row.next_attempt_at + timedelta(seconds=1)
    assert (await auth_erase.process_outbox(later))["done"] == 1
    row = (await _outbox())[0]
    assert row.status == "done" and row.phone_sealed == "" and row.finished_at is not None  # the number is gone
    assert auth_state["calls"] == [E164, E164, E164]
    assert (await auth_erase.process_outbox(later + timedelta(days=8)))["purged"] == 1
    assert await _outbox() == []


@pytest.mark.asyncio
async def test_after_the_maximum_age_it_gives_up_blanks_the_number_and_says_so_without_it(client, auth_state, caplog):
    from datetime import timedelta

    from app.services import auth_erase

    await auth_erase.tell_auth(E164)
    row = (await _outbox())[0]
    caplog.set_level("ERROR")
    out = await auth_erase.process_outbox(row.created_at + auth_erase.max_age() + timedelta(days=1))
    assert out["gave_up"] == 1
    row = (await _outbox())[0]
    assert row.status == "gave_up" and row.phone_sealed == ""
    assert "GIVEN UP" in caplog.text and E164 not in caplog.text


@pytest.mark.asyncio
async def test_sso_switched_off_meanwhile_finishes_the_row_and_an_unreadable_seal_gives_up(client, auth_state, monkeypatch):
    from datetime import timedelta

    from app.services import auth_erase

    await auth_erase.tell_auth(E164)
    row = (await _outbox())[0]
    auth_state["answer"] = None
    assert (await auth_erase.process_outbox(row.next_attempt_at + timedelta(seconds=1)))["done"] == 1
    auth_state["answer"] = False
    await auth_erase.tell_auth(E164)
    monkeypatch.setenv("FIDELIA_ENCRYPTION_KEY", "another-key-entirely")  # rotated: the seal cannot be opened
    second = (await _outbox())[-1]
    assert (await auth_erase.process_outbox(second.next_attempt_at + timedelta(seconds=1)))["gave_up"] == 1


@pytest.mark.asyncio
async def test_a_failure_to_queue_never_breaks_the_deletion(client, auth_state, monkeypatch):
    from app.services import auth_erase

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(auth_erase.secretbox, "seal", lambda p: (_ for _ in ()).throw(RuntimeError("no key")))
    await auth_erase.tell_auth(E164)  # does not raise


# --- people who sign in only through auth have no users row: everything still works for them -------------------------------


@pytest.mark.asyncio
async def test_a_sso_only_customer_can_delete_her_account(client, monkeypatch):
    from app.api import account as account_api
    from app.core import security

    sso_user = {"username": KEY, "role": "customer", "sso": True, "principal": None, "token": "t"}
    async with AsyncSessionLocal() as db:
        row = await account_api._phone_account(db, sso_user)  # opens her row from the verified number
        await db.commit()
        assert row.phone_e164 == E164 and row.roles == "customer"
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(models.User).where(models.User.phone_e164 == E164))).scalar() == 1
        again = await account_api._phone_account(db, sso_user)  # the second time it finds the same row
        assert again.phone_e164 == E164
    legacy = {"username": KEY, "role": "customer"}  # a token that is not from auth never opens a row on its own
    async with AsyncSessionLocal() as db:
        await db.execute(models.User.__table__.delete())
        await db.commit()
    async with AsyncSessionLocal() as db:
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await account_api._phone_account(db, legacy)


@pytest.mark.asyncio
async def test_the_auth_hook_moves_a_sso_only_customers_data_without_a_users_row(client, monkeypatch):
    monkeypatch.setenv("FIDELIA_AUTH_HOOK_KEY", "k" * 32)
    new_e164 = "+2250755555555"
    async with AsyncSessionLocal() as db:
        db.add(models.LoyaltyConsent(customer_id=KEY, source="app", consent_version="fidelite-2026-10", granted_at=datetime(2026, 11, 1)))
        await db.commit()
    r = await client.post("/api/internal/phone-changed", json={"old_phone": E164, "new_phone": new_e164}, headers={"X-Service-Key": "k" * 32})
    assert r.status_code == 200 and r.json() == {"ok": True, "moved": True}
    async with AsyncSessionLocal() as db:
        keys = (await db.execute(select(models.LoyaltyConsent.customer_id))).scalars().all()
        assert keys == ["tel:" + new_e164]  # the data followed, though she never had a users row
    # a users row on the NEW number is someone else's account
    async with AsyncSessionLocal() as db:
        db.add(models.User(phone_e164="+2250766666666", roles="customer", disabled=False, created_at=datetime(2026, 11, 1)))
        await db.commit()
    taken = await client.post("/api/internal/phone-changed", json={"old_phone": new_e164, "new_phone": "+2250766666666"}, headers={"X-Service-Key": "k" * 32})
    assert taken.status_code == 409
