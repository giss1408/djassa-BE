import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from app import models
from app.db import AsyncSessionLocal
from app.services import account_checks as ac
from app.services.whatsapp import whatsapp_link

NOW = datetime(2026, 10, 22, 12, 0, 0)


def _text(link: str) -> str:
    return parse_qs(urlparse(link).query)["text"][0]


def _code(link: str) -> str:
    return re.search(r"(\d{3}) (\d{3})", _text(link)).expand(r"\1\2")


async def _user(db, phone):
    u = models.User(phone_e164=phone, roles="customer", created_at=NOW)
    db.add(u)
    await db.flush()
    return u


def test_link_encodes_number_and_text():
    link = whatsapp_link("+2250701020304", "Bonjour, ça va ?")
    assert link.startswith("https://wa.me/2250701020304?text=Bonjour")
    assert _text(link) == "Bonjour, ça va ?"


@pytest.mark.asyncio
async def test_code_message_spaces_the_code():
    async with AsyncSessionLocal() as db:
        u = await _user(db, "+2250800000101")
        check = await ac.open_check(db, u, "verify_number", NOW)
        link = await ac.send_check(db, check, 7, NOW)
        await db.commit()
        text = _text(link)
        assert re.search(r"code Fidelia : \d{3} \d{3}\. Saisissez-le", text)
        assert check.status == "sent" and check.sent_by == "7"
        assert check.expires_at == NOW + timedelta(hours=24) and check.attempts == 0
        assert link.startswith("https://wa.me/2250800000101?")


@pytest.mark.asyncio
async def test_open_check_reuses_the_open_one():
    async with AsyncSessionLocal() as db:
        u = await _user(db, "+2250800000102")
        a = await ac.open_check(db, u, "verify_number", NOW)
        await db.commit()
        b = await ac.open_check(db, u, "verify_number", NOW)
        assert a.id == b.id
        c = await ac.open_check(db, u, "reset_password", NOW)
        assert c.id != a.id
        await ac.refuse(db, a, NOW)
        await db.commit()
        d = await ac.open_check(db, u, "verify_number", NOW)
        assert d.id != a.id and a.status == "refused" and a.secret_hash is None


@pytest.mark.asyncio
async def test_resend_voids_the_previous_code():
    async with AsyncSessionLocal() as db:
        u = await _user(db, "+2250800000103")
        check = await ac.open_check(db, u, "verify_number", NOW)
        first = _code(await ac.send_check(db, check, 1, NOW))
        second = _code(await ac.send_check(db, check, 1, NOW))
        await db.commit()
        if first != second:
            with pytest.raises(ac.BadCode):
                await ac.verify_code(db, u, "verify_number", first, NOW)
        done = await ac.verify_code(db, u, "verify_number", second, NOW)
        assert done.status == "done" and done.done_at == NOW


@pytest.mark.asyncio
async def test_code_expires_after_24h():
    async with AsyncSessionLocal() as db:
        u = await _user(db, "+2250800000104")
        check = await ac.open_check(db, u, "verify_number", NOW)
        code = _code(await ac.send_check(db, check, 1, NOW))
        await db.commit()
        with pytest.raises(ac.BadCode):
            await ac.verify_code(db, u, "verify_number", code, NOW + timedelta(hours=24, seconds=1))


@pytest.mark.asyncio
async def test_five_wrong_codes_send_the_check_back_to_pending():
    async with AsyncSessionLocal() as db:
        u = await _user(db, "+2250800000105")
        check = await ac.open_check(db, u, "verify_number", NOW)
        code = _code(await ac.send_check(db, check, 1, NOW))
        await db.commit()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            with pytest.raises(ac.BadCode):
                await ac.verify_code(db, u, "verify_number", wrong, NOW)
        await db.refresh(check)
        assert check.status == "pending" and check.secret_hash is None
        with pytest.raises(ac.BadCode):
            await ac.verify_code(db, u, "verify_number", code, NOW)


@pytest.mark.asyncio
async def test_change_number_message_goes_to_the_new_number():
    async with AsyncSessionLocal() as db:
        u = await _user(db, "+2250800000106")
        check = await ac.open_check(db, u, "change_number", NOW, new_phone_e164="+2250800000107")
        link = await ac.send_check(db, check, 1, NOW)
        assert link.startswith("https://wa.me/2250800000107?")
        code = _code(link)
        assert (await ac.verify_code(db, u, "change_number", code, NOW)).new_phone_e164 == "+2250800000107"


@pytest.mark.asyncio
async def test_temporary_password_works_once():
    async with AsyncSessionLocal() as db:
        u = await _user(db, "+2250800000108")
        check = await ac.open_check(db, u, "reset_password", NOW)
        text = _text(await ac.send_check(db, check, 1, NOW))
        await db.commit()
        pw = re.search(r"Fidelia : (\S{10})\. Vous", text).group(1)
        assert set(pw) <= set("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789")
        assert not await ac.use_temporary_password(db, u, "wrongwrong", NOW)
        assert not await ac.use_temporary_password(db, u, pw, NOW + timedelta(hours=25))
        assert await ac.use_temporary_password(db, u, pw, NOW)
        assert not await ac.use_temporary_password(db, u, pw, NOW)
