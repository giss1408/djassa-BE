import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_consent_and_export():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_resp = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        assert token_resp.status_code == 200
        token = token_resp.json()["access_token"]

        # create merchant txn
        await ac.post(
            "/api/transactions",
            json={"merchant_id": 42, "user_id": "u42", "amount": 12.5, "currency": "XOF", "type": "sale"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # no consent yet
        r = await ac.get(f"/api/export/merchant/42", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

        # create consent
        rc = await ac.post(
            "/api/consents",
            json={"user_id": "demo", "merchant_id": 42, "scope": "transactions:export"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rc.status_code == 201

        # now export
        rex = await ac.get(f"/api/export/merchant/42", headers={"Authorization": f"Bearer {token}"})
        assert rex.status_code == 200
        assert "id,merchant_id,user_id" in rex.text