"""The investor brief is served only behind its password."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

PASSWORD = "correct-horse-battery"


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setenv("INVESTOR_BRIEF_PASSWORD", PASSWORD)
    monkeypatch.setenv("INVESTOR_BRIEF_LOGIN_LIMIT", "1000/minute")
    monkeypatch.delenv("FIDELIA_SITE_URL", raising=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
        yield ac


async def _sign_in(ac, next_path="/brief/"):
    return await ac.post("/brief/login", data={"password": PASSWORD, "next": next_path, "lang": "fr"})


@pytest.mark.asyncio
async def test_nothing_is_readable_without_the_password(client):
    for path in ("/brief/", "/brief/en.html", "/brief/index.html", "/brief/nda.html"):
        r = await client.get(path)
        assert r.status_code == 200
        assert 'name="password"' in r.text, f"{path} must show the login page"
        assert "La levée" not in r.text and "The ask" not in r.text, f"{path} leaked the brief"
        assert r.headers["cache-control"] == "private, no-store"

    pdf = await client.get("/brief/lettre-interet-imf.pdf")
    assert pdf.status_code == 303
    assert pdf.headers["location"] == "/brief/?next=/brief/lettre-interet-imf.pdf"


@pytest.mark.asyncio
async def test_the_login_page_itself_has_its_style(client):
    css = await client.get("/brief/brief.css")
    assert css.status_code == 200 and ".login" in css.text
    assert (await client.get("/brief/favicon.svg")).status_code == 200


@pytest.mark.asyncio
async def test_wrong_password_is_refused(client):
    r = await client.post("/brief/login", data={"password": "guess-guess-guess", "next": "/brief/"})
    assert r.status_code == 401
    assert "fidelia_brief" not in r.headers.get("set-cookie", "")
    assert "Mot de passe incorrect" in r.text


@pytest.mark.asyncio
async def test_the_right_password_opens_the_brief_and_the_letters(client):
    r = await _sign_in(client)
    assert r.status_code == 303 and r.headers["location"] == "/brief/"
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Path=/brief" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()

    home = await client.get("/brief/")
    assert "La levée" in home.text and 'name="password"' not in home.text
    english = await client.get("/brief/en.html")
    assert "The ask" in english.text
    pdf = await client.get("/brief/lettre-interet-commercant.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # Without FIDELIA_SITE_URL, the "Website" link is dropped, not left broken.
    assert "__SITE_URL__" not in english.text


@pytest.mark.asyncio
async def test_after_signing_in_the_reader_lands_where_they_were_going(client):
    r = await _sign_in(client, next_path="/brief/lettre-interet-imf.pdf")
    assert r.headers["location"] == "/brief/lettre-interet-imf.pdf"


@pytest.mark.asyncio
async def test_no_redirect_to_another_site(client):
    for evil in ("https://evil.example/", "//evil.example/", "/brief/../../etc/passwd", "/api/token"):
        r = await _sign_in(client, next_path=evil)
        assert r.headers["location"] == "/brief/", evil


@pytest.mark.asyncio
async def test_only_brief_files_are_served(client):
    await _sign_in(client)
    for path in ("/brief/..%2Fapi%2Finvestor_brief.py", "/brief/OFL.txt", "/brief/missing.html", "/brief/main.py"):
        r = await client.get(path)
        assert r.status_code == 404, path


@pytest.mark.asyncio
async def test_changing_the_password_signs_everyone_out(client, monkeypatch):
    await _sign_in(client)
    assert "La levée" in (await client.get("/brief/")).text

    monkeypatch.setenv("INVESTOR_BRIEF_PASSWORD", "a-brand-new-password")
    again = await client.get("/brief/")
    assert 'name="password"' in again.text


@pytest.mark.asyncio
async def test_a_forged_cookie_is_ignored(client):
    client.cookies.set("fidelia_brief", "eyJwIjoiMTIzIn0.forged.signature", domain="test", path="/brief")
    r = await client.get("/brief/")
    assert 'name="password"' in r.text


@pytest.mark.asyncio
async def test_closed_when_no_password_or_a_weak_one_is_set(client, monkeypatch):
    for value in (None, "short"):
        if value is None:
            monkeypatch.delenv("INVESTOR_BRIEF_PASSWORD")
        else:
            monkeypatch.setenv("INVESTOR_BRIEF_PASSWORD", value)
        r = await client.get("/brief/")
        assert r.status_code == 503 and 'name="password"' not in r.text
        login = await client.post("/brief/login", data={"password": value or "anything-at-all"})
        assert login.status_code == 503


@pytest.mark.asyncio
async def test_the_website_link_points_at_the_public_site(client, monkeypatch):
    monkeypatch.setenv("FIDELIA_SITE_URL", "https://fidelia.example/")
    await _sign_in(client)
    r = await client.get("/brief/en.html")
    assert 'href="https://fidelia.example/"' in r.text


@pytest.mark.asyncio
async def test_password_attempts_are_rate_limited(client, monkeypatch):
    monkeypatch.setenv("INVESTOR_BRIEF_LOGIN_LIMIT", "3/minute")
    codes = []
    for _ in range(5):
        r = await client.post(
            "/brief/login", data={"password": "nope-nope-nope"}, headers={"X-Forwarded-For": "203.0.113.7"}
        )
        codes.append(r.status_code)
    assert 429 in codes
