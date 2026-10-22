"""Forgotten and changed passwords."""

import re
from datetime import timedelta
from urllib.parse import unquote

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api.auth import utcnow
from app.core.phone import normalize_phone
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data
from app.services import account_checks
from tests.helpers import make_user, sign_in

PHONE = "0701020304"
E164 = normalize_phone(PHONE, "CI")
ANSWER = "Si ce numero a un compte, Fidelia vous enverra un mot de passe temporaire sur WhatsApp."


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


async def _ask(ac, phone=PHONE):
    return await ac.post("/api/auth/password-reset", json={"phone": phone, "country_code": "CI"})


async def _send_temporary(sent_at=None):
    """What the admin app does: send the open reset check, read the password from the link."""
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()
        check = (
            await db.execute(
                select(models.AccountCheck).where(
                    models.AccountCheck.user_id == user.id,
                    models.AccountCheck.kind == "reset_password",
                    models.AccountCheck.status.in_(("pending", "sent")),
                )
            )
        ).scalars().first()
        link = await account_checks.send_check(db, check, 1, sent_at or utcnow())
        await db.commit()
    text = unquote(link).replace("+", " ")
    return re.search(r"temporaire Fidelia : (\S+?)\. ", text).group(1)


async def _checks(kind="reset_password"):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.AccountCheck).where(models.AccountCheck.kind == kind))).scalars().all()


@pytest.mark.asyncio
async def test_reset_answer_is_the_same_for_unknown_numbers(client):
    await make_user(PHONE)
    known = await _ask(client)
    unknown = await _ask(client, "0799999999")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"message": ANSWER}
    assert len(await _checks()) == 1
    # Asking twice reuses the open check.
    await _ask(client)
    assert len(await _checks()) == 1


@pytest.mark.asyncio
async def test_reset_for_a_disabled_user_opens_nothing(client):
    await make_user(PHONE)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == E164))).scalar_one()
        user.disabled = True
        await db.commit()
    r = await _ask(client)
    assert r.status_code == 202 and r.json() == {"message": ANSWER}
    assert await _checks() == []


@pytest.mark.asyncio
async def test_temporary_password_forces_a_change(client):
    await make_user(PHONE, verified=False)
    await _ask(client)
    temp = await _send_temporary()
    r = await sign_in(client, PHONE, password=temp)
    assert r.status_code == 200, r.text
    pair = r.json()
    assert pair["must_change_password"] is True and pair["verified"] is True
    r = await client.get("/api/customer/loyalty", headers=_auth(pair))
    assert r.status_code == 403 and r.json()["detail"] == "password_change_required"
    # The password is single use.
    assert (await sign_in(client, PHONE, password=temp)).status_code == 401
    # A pc session may change the password without knowing an old one.
    r = await client.post("/api/auth/password", headers=_auth(pair), json={"new": "nouveaumdp9"})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["must_change_password"] is False
    assert (await client.get("/api/customer/loyalty", headers=_auth(new))).status_code == 200
    assert (await sign_in(client, PHONE, password="nouveaumdp9")).status_code == 200


@pytest.mark.asyncio
async def test_password_change_signs_out_other_sessions(client):
    await make_user(PHONE)
    first = (await sign_in(client, PHONE)).json()
    second = (await sign_in(client, PHONE)).json()
    bad = await client.post(
        "/api/auth/password", headers=_auth(second), json={"current": "pasbon12345", "new": "nouveaumdp9"}
    )
    assert bad.status_code == 401 and bad.json()["detail"] == "Mot de passe actuel incorrect."
    weak = await client.post("/api/auth/password", headers=_auth(second), json={"current": "motdepasse1", "new": "a"})
    assert weak.status_code == 422
    r = await client.post(
        "/api/auth/password", headers=_auth(second), json={"current": "motdepasse1", "new": "nouveaumdp9"}
    )
    assert r.status_code == 200, r.text
    new = r.json()
    assert (await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": second["refresh_token"]})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": new["refresh_token"]})).status_code == 200


@pytest.mark.asyncio
async def test_temporary_password_expires_after_24h(client):
    await make_user(PHONE)
    await _ask(client)
    temp = await _send_temporary(sent_at=utcnow() - timedelta(hours=25))
    assert (await sign_in(client, PHONE, password=temp)).status_code == 401


@pytest.mark.asyncio
async def test_old_password_still_works_until_the_temporary_one_is_used(client):
    await make_user(PHONE)
    await _ask(client)
    temp = await _send_temporary()
    r = await sign_in(client, PHONE)
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    r = await sign_in(client, PHONE, password=temp)
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    # Once used, the old password still works until it is replaced.
    assert (await sign_in(client, PHONE)).json()["must_change_password"] is True


@pytest.mark.asyncio
async def test_wrong_temporary_password_counts_towards_the_lockout(client):
    await make_user(PHONE)
    await _ask(client)
    temp = await _send_temporary()
    for _ in range(5):
        assert (await sign_in(client, PHONE, password="Mauvais12345")).status_code in (401,)
    assert (await sign_in(client, PHONE, password=temp)).status_code == 423


@pytest.mark.asyncio
async def test_team_created_login_without_password_uses_the_temporary_one(client):
    await make_user(PHONE, password=None, verified=False)
    assert (await sign_in(client, PHONE)).status_code == 409
    await _ask(client)
    temp = await _send_temporary()
    r = await sign_in(client, PHONE, password=temp)
    assert r.status_code == 200 and r.json()["must_change_password"] is True
