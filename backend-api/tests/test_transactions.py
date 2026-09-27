import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_create_and_list_transactions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_resp = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        assert token_resp.status_code == 200
        token = token_resp.json()["access_token"]

        # create a transaction
        r = await ac.post(
            "/api/transactions",
            json={"merchant_id": 1, "user_id": "u1", "amount": 25.0, "currency": "XOF", "type": "sale"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        tx = r.json()
        assert tx["merchant_id"] == 1
        assert tx["user_id"] == "demo"

        # list transactions
        r2 = await ac.get("/api/transactions/merchant/1", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        items = r2.json()
        assert isinstance(items, list)
        assert len(items) >= 1

        other_token = create_access_token({"sub": "other-user"})
        other_response = await ac.get(
            "/api/transactions/merchant/1",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert other_response.status_code == 200
        assert other_response.json() == []


@pytest.mark.asyncio
async def test_transaction_sync_is_idempotent():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_resp = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        operation = {
            "idempotency_key": "offline-operation-001",
            "merchant_id": 99,
            "user_id": "ignored",
            "amount": "12.50",
            "currency": "XOF",
            "type": "sale",
        }

        first = await ac.post("/api/transactions/sync", json={"operations": [operation]}, headers=headers)
        second = await ac.post("/api/transactions/sync", json={"operations": [operation]}, headers=headers)

        assert first.status_code == 200
        assert first.json()["results"][0]["status"] == "accepted"
        assert second.status_code == 200
        assert second.json()["results"][0]["status"] == "already_processed"
        assert first.json()["results"][0]["transaction"]["id"] == second.json()["results"][0]["transaction"]["id"]

        changed = {**operation, "amount": "99.00"}
        conflict = await ac.post("/api/transactions/sync", json={"operations": [changed]}, headers=headers)
        assert conflict.json()["results"][0]["status"] == "rejected"