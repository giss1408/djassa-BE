"""The script that gives the first admin a password."""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import models
from app.core.passwords import verify_password
from app.db import AsyncSessionLocal, Base, engine
from app.scripts import set_password

PHONE = "+2250700000099"


@pytest_asyncio.fixture(autouse=True)
async def fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def _answers(*values):
    it = iter(values)
    return lambda _prompt="": next(it)


async def _user():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.User).where(models.User.phone_e164 == PHONE))).scalar_one()


async def _make_admin():
    async with AsyncSessionLocal() as db:
        db.add(models.User(
            phone_e164=PHONE, roles="admin", disabled=False, created_at=set_password.utcnow(), must_change_password=True,
            failed_logins=4, locked_until=set_password.utcnow(),
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_script_sets_a_verified_password():
    await _make_admin()
    code = await set_password.run([PHONE], input=_answers("un-bon-mot-de-passe", "un-bon-mot-de-passe"))
    assert code == 0
    user = await _user()
    assert verify_password("un-bon-mot-de-passe", user.password_hash)
    assert user.phone_verified_at is not None
    assert user.must_change_password is False
    assert user.failed_logins == 0 and user.locked_until is None


@pytest.mark.asyncio
async def test_script_refuses_a_weak_password(capsys):
    await _make_admin()
    code = await set_password.run([PHONE], input=_answers("12345678", "12345678"))
    assert code == 1
    assert "uniquement de chiffres" in capsys.readouterr().out
    assert (await _user()).password_hash is None


@pytest.mark.asyncio
async def test_script_refuses_mismatch_and_unknown_number(capsys):
    await _make_admin()
    assert await set_password.run([PHONE], input=_answers("un-bon-mot-de-passe", "autre-chose-123")) == 1
    assert (await _user()).password_hash is None
    assert await set_password.run(["+2250700000098"], input=_answers("un-bon-mot-de-passe", "un-bon-mot-de-passe")) == 1
    assert "Numero inconnu. Accordez d'abord le role admin." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_main_wrapper_runs_the_script():
    await _make_admin()

    def call():
        return set_password.main([PHONE], input=_answers("un-bon-mot-de-passe", "un-bon-mot-de-passe"))

    code = await asyncio.get_running_loop().run_in_executor(None, call)
    assert code == 0
