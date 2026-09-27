import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_graphql_country_query():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/graphql",
            json={"query": "{ country(code: \"CI\") { code currency languages supportChannels } }"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["country"]["currency"] == "XOF"


@pytest.mark.asyncio
async def test_graphql_sync_requires_authentication():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/graphql",
            json={
                "query": "mutation { syncTransactions(operations: [{idempotencyKey: \"graphql-op-001\", merchantId: 7, amount: \"3.50\", currency: \"XOF\", type: \"sale\"}]) { status } }"
            },
        )
        assert response.status_code == 200
        assert "Authentication required" in response.text


@pytest.mark.asyncio
async def test_graphql_sync_transaction():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_response = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        token = token_response.json()["access_token"]
        response = await ac.post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": "mutation { syncTransactions(operations: [{idempotencyKey: \"graphql-op-002\", merchantId: 8, amount: \"3.50\", currency: \"XOF\", type: \"sale\"}]) { status transaction { amount userId } } }"
            },
        )
        assert response.status_code == 200
        result = response.json()["data"]["syncTransactions"][0]
        assert result["status"] == "accepted"
        assert result["transaction"]["userId"] == "demo"
