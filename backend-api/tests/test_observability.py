"""What production monitoring relies on: the /metrics gate, bounded metric
labels, request ids and access lines, and the daily SMS budget."""

import base64
import logging

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setenv("OTP_SENDER", "console")
    monkeypatch.setenv("OTP_DEV_ECHO", "1")
    monkeypatch.delenv("DJASSA_ENV", raising=False)
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


def _basic(password, user="12345"):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


@pytest.mark.asyncio
async def test_metrics_are_open_only_in_development(client, monkeypatch):
    assert (await client.get("/metrics")).status_code == 200

    # A deployed API without a token hides the endpoint altogether.
    monkeypatch.setenv("DJASSA_ENV", "test")
    assert (await client.get("/metrics")).status_code == 404


@pytest.mark.asyncio
async def test_metrics_need_the_token_once_one_is_set(client, monkeypatch):
    monkeypatch.setenv("DJASSA_ENV", "production")
    monkeypatch.setenv("METRICS_TOKEN", "s3cret-token")

    assert (await client.get("/metrics")).status_code == 404
    assert (await client.get("/metrics", headers={"Authorization": "Bearer wrong"})).status_code == 404
    assert (await client.get("/metrics", headers={"Authorization": _basic("wrong")})).status_code == 404
    assert (await client.get("/metrics", headers={"Authorization": "Basic not-base64!"})).status_code == 404

    bearer = await client.get("/metrics", headers={"Authorization": "Bearer s3cret-token"})
    assert bearer.status_code == 200
    assert "djassa_build_info" in bearer.text
    # Grafana Cloud's scrape job sends the token as the basic-auth password.
    assert (await client.get("/metrics", headers={"Authorization": _basic("s3cret-token")})).status_code == 200


@pytest.mark.asyncio
async def test_requests_are_counted_by_route_template(client):
    await client.get("/api/venues/1")
    await client.get("/api/venues/987654")
    await client.post("/api/webhooks/mobile-money", content=b"{}")
    await client.get("/wp-login.php")

    metrics = (await client.get("/metrics")).text
    assert 'path="/api/venues/{venue_id}"' in metrics
    assert "/api/venues/987654" not in metrics
    assert 'path="/api/webhooks/mobile-money"' in metrics
    assert 'path="unmatched"' in metrics
    assert "wp-login" not in metrics


@pytest.mark.asyncio
async def test_each_request_gets_an_id_and_one_access_line(client, caplog):
    caplog.set_level(logging.INFO, logger="djassa.access")
    r = await client.get("/api/venues/1?phone=0712345678")
    assert len(r.headers["X-Request-ID"]) == 32

    # A caller's well-formed id is kept, so a request can be followed end to end.
    kept = await client.get("/api/venues/1", headers={"X-Request-ID": "abc-12345678"})
    assert kept.headers["X-Request-ID"] == "abc-12345678"
    junk = await client.get("/api/venues/1", headers={"X-Request-ID": "<script>"})
    assert junk.headers["X-Request-ID"] != "<script>"

    lines = [rec for rec in caplog.records if rec.name == "djassa.access"]
    assert len(lines) == 3
    assert lines[0].fields["route"] == "/api/venues/{venue_id}"
    assert lines[0].fields["status"] == r.status_code
    assert lines[0].fields["request_id"] == r.headers["X-Request-ID"]
    # The query string (here a phone number) never reaches the log.
    assert all("0712345678" not in rec.getMessage() and "0712345678" not in str(rec.fields) for rec in lines)


@pytest.mark.asyncio
async def test_daily_sms_budget_pauses_codes_for_every_number(client, monkeypatch):
    monkeypatch.setenv("OTP_DAILY_SMS_BUDGET", "2")
    for phone in ("07 11 11 11 11", "07 22 22 22 22"):
        r = await client.post("/api/auth/otp/request", json={"phone": phone, "app": "customer"})
        assert r.status_code == 202, r.text

    # A third number, under every per-number and per-IP cap, still waits.
    r = await client.post("/api/auth/otp/request", json={"phone": "07 33 33 33 33", "app": "customer"})
    assert r.status_code == 503
    assert 'result="daily_budget"' in (await client.get("/metrics")).text
