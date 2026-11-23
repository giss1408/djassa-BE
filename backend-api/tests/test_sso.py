"""SSO dual-accept (platform `auth` tokens next to fidelia's own), step-up on sensitive routes, agents never set the wallet.
Tokens are signed here with a throwaway Ed25519 key and a local JWKS: no network, no auth service."""

import base64
import time

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient
from regisse_kit.sso import SsoVerifier

from app.core import sso
from app.core.security import create_access_token
from app.db import Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data

ISS = "http://auth.test"
PHONE = "+2250701020304"
KEY = Ed25519PrivateKey.generate()


def _jwks() -> dict:
    raw = KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"keys": [{"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "kid": "k1", "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode()}]}


def token(key=KEY, alg="EdDSA", **over) -> str:
    now = int(time.time())
    claims = {"iss": ISS, "aud": "fidelia", "sub": "7d2f6a1e-0000-4000-8000-000000000001", "ph": f"tel:{PHONE}", "role": "customer", "roles": ["customer"],
              "app": "customer", "amr": ["pwd"], "auth_time": now, "iat": now, "exp": now + 600, "sid": "s1", **over}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": "k1"})


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.delenv("FIDELIA_ENV", raising=False)
    for k in ("FIDELIA_SSO_ENABLED", "FIDELIA_REJECT_ROLELESS", "FIDELIA_SSO_MONEY_FAIL_CLOSED"):
        monkeypatch.delenv(k, raising=False)
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


@pytest.fixture
def sso_on(monkeypatch):
    monkeypatch.setenv("FIDELIA_SSO_ENABLED", "1")
    monkeypatch.setenv("FIDELIA_SSO_ISSUER", ISS)
    monkeypatch.setenv("FIDELIA_SSO_JWKS_URL", "http://auth.test/.well-known/jwks.json")
    v = SsoVerifier(issuer=ISS, audience="fidelia", jwks_fetch=_jwks)
    monkeypatch.setattr(sso, "_verifier", lambda: v)


async def admin_h(client):
    r = await client.post("/api/token", data={"username": "admin", "password": "admin123"})
    return bearer(r.json()["access_token"])


async def enrol(client, **over):
    shop = {"category": "maquis", "name": "Maquis Test", "commune": "Treichville", "merchant_phone": PHONE, **over}
    r = await client.post("/api/admin/venues", json=shop, headers=await admin_h(client))
    assert r.status_code == 201, r.text
    return r.json()


# --- dual-accept -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_off_by_default_an_sso_token_is_refused(client):
    assert (await client.get("/api/auth/me", headers=bearer(token()))).status_code == 401


@pytest.mark.asyncio
async def test_an_sso_customer_gets_fidelias_identity_from_the_phone_claim(client, sso_on):
    r = await client.get("/api/auth/me", headers=bearer(token()))
    assert r.status_code == 200
    assert r.json()["sub"] == f"tel:{PHONE}" and r.json()["role"] == "customer" and r.json()["phone_masked"]


@pytest.mark.asyncio
async def test_roles_are_mapped_and_super_admin_is_an_admin_for_fidelia(client, sso_on):
    t = token(role="super_admin", roles=["super_admin"], app="admin", amr=["pwd", "totp"])
    assert (await client.get("/api/admin/export-audits", headers=bearer(t))).status_code == 200
    # a customer token does not reach admin routes; a merchant token does not either
    assert (await client.get("/api/admin/export-audits", headers=bearer(token()))).status_code == 403
    assert (await client.get("/api/admin/export-audits", headers=bearer(token(role="merchant", roles=["merchant"], app="merchant")))).status_code == 403


@pytest.mark.asyncio
async def test_a_merchant_token_finds_the_shop_by_phone_key(client, sso_on):
    venue = await enrol(client, payout_provider="wave", payout_account=PHONE)
    r = await client.get("/api/merchant/pay-code", headers=bearer(token(role="merchant", roles=["merchant"], app="merchant")))
    assert r.status_code == 200 and r.json()["pay_code"] == venue["pay_code"]


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [{"aud": "flariane"}, {"iss": "http://evil"}, {"exp": 1, "iat": 0}, {"role": None}, {"role": "emperor"}, {"mcp": True},
                                  {"ph": None}, {"ph": "+2250701020304"}, {"ph": ""}, {"sid": None}])
async def test_bad_or_wrongly_scoped_tokens_are_refused(client, sso_on, over):
    assert (await client.get("/api/auth/me", headers=bearer(token(**over)))).status_code == 401


@pytest.mark.asyncio
async def test_forged_tokens_are_refused(client, sso_on):
    payload = jwt.decode(token(), options={"verify_signature": False})
    forged = [token(key=Ed25519PrivateKey.generate()),
              jwt.encode(payload, "test-only-jwt-secret", algorithm="HS256", headers={"kid": "k1"}),  # even signed with fidelia's own secret
              jwt.encode(payload, None, algorithm="none", headers={"kid": "k1"}), "garbage"]
    for t in forged:
        r = await client.get("/api/auth/me", headers=bearer(t))
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_fidelias_own_tokens_keep_working_with_sso_on(client, sso_on):
    own = create_access_token({"sub": f"tel:{PHONE}", "role": "customer"})
    assert (await client.get("/api/auth/me", headers=bearer(own))).status_code == 200
    r = await client.post("/api/token", data={"username": "demo", "password": "demo123"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_an_auth_outage_does_not_break_valid_tokens(client, sso_on, monkeypatch):
    # the JWKS is cached by the verifier: even if the fetch fails later, a verified key keeps verifying
    assert (await client.get("/api/auth/me", headers=bearer(token()))).status_code == 200
    v = SsoVerifier(issuer=ISS, audience="fidelia", jwks_fetch=lambda: (_ for _ in ()).throw(RuntimeError("auth down")))
    monkeypatch.setattr(sso, "_verifier", lambda: v)
    assert (await client.get("/api/auth/me", headers=bearer(token()))).status_code == 401  # a NEW verifier with no cached key cannot verify: clean 401, not 500


# --- the old "no role = merchant" default ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roleless_legacy_tokens_are_merchants_until_the_flag_turns_that_off(client, monkeypatch):
    t = create_access_token({"sub": f"tel:{PHONE}"})  # no role claim
    assert (await client.get("/api/auth/me", headers=bearer(t))).json()["role"] == "merchant"  # today's behaviour, kept for compatibility
    monkeypatch.setenv("FIDELIA_REJECT_ROLELESS", "1")
    assert (await client.get("/api/auth/me", headers=bearer(t))).status_code == 401
    # tokens that carry a role are untouched
    ok = create_access_token({"sub": f"tel:{PHONE}", "role": "customer"})
    assert (await client.get("/api/auth/me", headers=bearer(ok))).status_code == 200


# --- step-up on sensitive routes ----------------------------------------------------------------------------------------------

WAVE = {"api_key": "wave_ci_prod_" + "k" * 40, "webhook_secret": "wave_ci_WHS_" + "s" * 30}


def _guard_passed(r) -> bool:
    return r.status_code not in (401, 403, 503) or r.json().get("detail") not in ("step_up_required", "sso_session_ended", "sso_unavailable")


@pytest.mark.asyncio
async def test_wallet_change_needs_a_fresh_proof_for_sso_sessions(client, sso_on, monkeypatch):
    await enrol(client)
    merchant = dict(role="merchant", roles=["merchant"], app="merchant")

    async def alive(_t):
        return True

    monkeypatch.setattr(sso, "session_alive", alive)
    old = token(**merchant, auth_time=int(time.time()) - 3600)
    r = await client.put("/api/merchant/wave", json=WAVE, headers=bearer(old))
    assert r.status_code == 403 and r.json()["detail"] == "step_up_required"
    fresh = token(**merchant, auth_time=int(time.time()) - 30)
    assert _guard_passed(await client.put("/api/merchant/wave", json=WAVE, headers=bearer(fresh)))
    # the same guard protects removing the wallet, staff changes and exports
    for method, path, kw in (("delete", "/api/merchant/wave", {}), ("post", "/api/merchant/staff", {"json": {"phone": "0509090909"}}),
                             ("get", "/api/export/merchant/revenue.csv", {}), ("get", "/api/export/merchant/customers.csv", {})):
        r = await getattr(client, method)(path, headers=bearer(old), **kw)
        assert r.status_code == 403 and r.json()["detail"] == "step_up_required", path


@pytest.mark.asyncio
async def test_a_session_ended_at_auth_stops_money_routes_even_with_a_fresh_proof(client, sso_on, monkeypatch):
    await enrol(client)
    t = token(role="merchant", roles=["merchant"], app="merchant")

    async def dead(_t):
        return False

    monkeypatch.setattr(sso, "session_alive", dead)
    r = await client.put("/api/merchant/wave", json=WAVE, headers=bearer(t))
    assert r.status_code == 401 and r.json()["detail"] == "sso_session_ended"


@pytest.mark.asyncio
async def test_auth_unreachable_fails_closed_on_money_routes_unless_told_otherwise(client, sso_on, monkeypatch):
    await enrol(client)
    t = token(role="merchant", roles=["merchant"], app="merchant")

    async def unreachable(_t):
        return None

    monkeypatch.setattr(sso, "session_alive", unreachable)
    r = await client.put("/api/merchant/wave", json=WAVE, headers=bearer(t))
    assert r.status_code == 503 and r.json()["detail"] == "sso_unavailable"
    monkeypatch.setenv("FIDELIA_SSO_MONEY_FAIL_CLOSED", "0")
    assert _guard_passed(await client.put("/api/merchant/wave", json=WAVE, headers=bearer(t)))


@pytest.mark.asyncio
async def test_admin_actions_need_the_authenticator_code_to_be_recent(client, sso_on, monkeypatch):
    async def alive(_t):
        return True

    monkeypatch.setattr(sso, "session_alive", alive)
    admin = dict(role="admin", roles=["admin"], app="admin")
    body = {"phone": "0701020304", "disabled": True}
    no_code = token(**admin, amr=["pwd"])
    r = await client.post("/api/admin/users/disable", json=body, headers=bearer(no_code))
    assert r.status_code == 403 and r.json()["detail"] == "step_up_required"
    stale = token(**admin, amr=["pwd", "totp"], auth_time=int(time.time()) - 3600)
    assert (await client.post("/api/admin/users/disable", json=body, headers=bearer(stale))).json()["detail"] == "step_up_required"
    good = token(**admin, amr=["pwd", "totp"])
    assert _guard_passed(await client.post("/api/admin/users/disable", json=body, headers=bearer(good)))
    for path in ("/api/admin/users/roles", "/api/admin/users/revoke-sessions", "/api/admin/users/roles/revoke"):
        r = await client.post(path, json={"phone": "0701020304", "role": "merchant"}, headers=bearer(no_code))
        assert r.status_code == 403 and r.json()["detail"] == "step_up_required", path


@pytest.mark.asyncio
async def test_fidelias_own_tokens_are_not_subject_to_step_up_until_they_are_retired(client, sso_on):
    await enrol(client)
    own = create_access_token({"sub": f"tel:{PHONE}", "role": "merchant"})
    r = await client.put("/api/merchant/wave", json=WAVE, headers=bearer(own))
    assert _guard_passed(r)  # reaches the handler: the existing behaviour is unchanged


# --- agents never set the wallet ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_cannot_set_the_wallet_at_enrolment_but_can_enrol_the_shop(client):
    agent = bearer(create_access_token({"sub": "tel:+2250709090909", "role": "agent"}))
    shop = {"category": "maquis", "name": "Maquis Agent", "commune": "Cocody", "merchant_phone": PHONE}
    bad = await client.post("/api/admin/venues", json={**shop, "payout_provider": "wave", "payout_account": PHONE}, headers=agent)
    assert bad.status_code == 422 and bad.json()["detail"] == "wallet_set_by_merchant"
    ok = await client.post("/api/admin/venues", json=shop, headers=agent)
    assert ok.status_code == 201 and ok.json()["pay_code"] is None  # listed, loyalty works, no pay QR until the merchant adds his wallet


@pytest.mark.asyncio
async def test_an_admin_can_still_set_the_wallet(client):
    shop = {"category": "maquis", "name": "Maquis Admin", "commune": "Cocody", "merchant_phone": PHONE, "payout_provider": "wave", "payout_account": PHONE}
    r = await client.post("/api/admin/venues", json=shop, headers=await admin_h(client))
    assert r.status_code == 201 and r.json()["pay_code"]
