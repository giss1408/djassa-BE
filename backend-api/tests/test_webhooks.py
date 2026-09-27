import hashlib
import hmac
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

SECRET = "dev-secret"


def _sign(raw: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_mobile_money_webhook(monkeypatch):
    # The endpoint fails closed: with no MOBILE_MONEY_SECRETS configured it
    # rejects everything, so the test configures one (current key first,
    # previous key after, as during a rotation).
    monkeypatch.setenv("MOBILE_MONEY_SECRETS", f"{SECRET},old-secret")
    from app.main import app

    raw = json.dumps({"transaction_id": f"tx-{uuid.uuid4().hex}", "amount": 1000}).encode()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/webhooks/mobile-money", content=raw, headers={"x-signature": _sign(raw)})
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # A replay of the same event is acknowledged without being processed twice.
        resp = await ac.post("/api/webhooks/mobile-money", content=raw, headers={"x-signature": _sign(raw)})
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_processed"

        # Still valid under the previous key during a rotation.
        raw2 = json.dumps({"transaction_id": f"tx-{uuid.uuid4().hex}", "amount": 500}).encode()
        resp = await ac.post("/api/webhooks/mobile-money", content=raw2, headers={"x-signature": _sign(raw2, "old-secret")})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_mobile_money_webhook_rejects_bad_or_missing_signature(monkeypatch):
    monkeypatch.setenv("MOBILE_MONEY_SECRETS", SECRET)
    from app.main import app

    raw = json.dumps({"transaction_id": f"tx-{uuid.uuid4().hex}", "amount": 1000}).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/webhooks/mobile-money", content=raw, headers={"x-signature": _sign(raw, "wrong")})
        assert resp.status_code == 401
        resp = await ac.post("/api/webhooks/mobile-money", content=raw)
        assert resp.status_code == 401
