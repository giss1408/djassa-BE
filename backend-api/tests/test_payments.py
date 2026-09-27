import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_create_payment():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # get token
        token_resp = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        assert token_resp.status_code == 200
        token = token_resp.json()["access_token"]

        r = await ac.post(
            "/api/payments",
            json={"amount": 10.5, "currency": "XOF", "recipient_id": "user-1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["id"] >= 1
        assert data["amount"] == 10.5
