"""The API behind Cloudflare: which address a request counts against, and the
origin secret that proves a request came through Cloudflare (app/edge.py)."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app import edge
from app.main import app
from app.rate_limiter import limiter


def _request(headers: dict[str, str], peer: str = "10.0.0.9") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 1234),
    })


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def test_a_forged_forwarded_for_does_not_change_the_address(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ORIGIN_SECRET", raising=False)
    # The caller wrote the first entry; Render's proxy appended the last one.
    forged = _request({"X-Forwarded-For": "1.2.3.4, 41.66.10.20"})
    other = _request({"X-Forwarded-For": "5.6.7.8, 41.66.10.20"})
    assert edge.client_ip(forged) == edge.client_ip(other) == "41.66.10.20"


def test_without_forwarded_for_the_peer_is_the_address(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ORIGIN_SECRET", raising=False)
    assert edge.client_ip(_request({})) == "10.0.0.9"


def test_behind_cloudflare_the_address_is_cloudflares_view_of_the_caller(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ORIGIN_SECRET", "s3cret-current")
    request = _request({
        "X-Origin-Auth": "s3cret-current",
        "CF-Connecting-IP": "41.66.10.20",
        "X-Forwarded-For": "1.2.3.4, 41.66.10.20, 172.70.1.1",
    })
    assert edge.client_ip(request) == "41.66.10.20"


def test_cf_connecting_ip_is_ignored_without_the_origin_secret(monkeypatch):
    # Someone calling the onrender.com address directly can send any header.
    monkeypatch.delenv("CLOUDFLARE_ORIGIN_SECRET", raising=False)
    request = _request({"CF-Connecting-IP": "9.9.9.9", "X-Forwarded-For": "41.66.10.20"})
    assert edge.client_ip(request) == "41.66.10.20"


@pytest.mark.asyncio
async def test_forged_addresses_share_one_rate_limit(client, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ORIGIN_SECRET", raising=False)
    monkeypatch.setenv("PUBLIC_READ_RATE_LIMIT", "3/minute")
    limiter.reset()
    codes = [
        (await client.get("/api/deals", headers={"X-Forwarded-For": f"10.9.9.{i}, 41.66.10.20"})).status_code
        for i in range(4)
    ]
    limiter.reset()
    assert codes == [200, 200, 200, 429]


@pytest.mark.asyncio
async def test_with_an_origin_secret_requests_that_skip_cloudflare_are_refused(client, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ORIGIN_SECRET", "s3cret-current")
    assert (await client.get("/api/categories")).status_code == 403
    assert (await client.get("/api/categories", headers={"X-Origin-Auth": "wrong"})).status_code == 403
    assert (await client.get("/api/categories", headers={"X-Origin-Auth": "s3cret-current"})).status_code == 200


@pytest.mark.asyncio
async def test_the_previous_origin_secret_still_works_while_rotating(client, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ORIGIN_SECRET", "s3cret-new,s3cret-old")
    assert (await client.get("/api/categories", headers={"X-Origin-Auth": "s3cret-old"})).status_code == 200
    assert (await client.get("/api/categories", headers={"X-Origin-Auth": "s3cret-new"})).status_code == 200


@pytest.mark.asyncio
async def test_health_and_metrics_do_not_need_the_origin_secret(client, monkeypatch):
    # Render's health check and the private-network metrics scraper call the
    # instance directly. /metrics keeps its own token (app/observability.py).
    monkeypatch.setenv("CLOUDFLARE_ORIGIN_SECRET", "s3cret-current")
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/metrics")).status_code == 200


def test_production_refuses_in_memory_rate_limits(monkeypatch):
    monkeypatch.setenv("FIDELIA_ENV", "production")
    monkeypatch.setenv("CLOUDFLARE_ORIGIN_SECRET", "a" * 40)
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)
    with pytest.raises(RuntimeError, match="RATE_LIMIT_STORAGE_URI"):
        edge.check_settings()
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "redis://red-example:6379")
    edge.check_settings()


def test_production_refuses_to_run_without_an_origin_secret(monkeypatch):
    monkeypatch.setenv("FIDELIA_ENV", "production")
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "redis://red-example:6379")
    monkeypatch.delenv("CLOUDFLARE_ORIGIN_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="CLOUDFLARE_ORIGIN_SECRET"):
        edge.check_settings()


def test_an_origin_secret_must_be_long(monkeypatch):
    monkeypatch.delenv("FIDELIA_ENV", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ORIGIN_SECRET", "short")
    with pytest.raises(RuntimeError, match="at least 32"):
        edge.check_settings()
