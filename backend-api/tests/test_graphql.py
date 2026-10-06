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


@pytest.mark.asyncio
async def test_graphql_my_sales_reads_the_merged_stream():
    """`mySales` takes no merchant id: the venue comes from the token.

    The deprecated `myTransactions` still accepts one, which is exactly why it is
    deprecated (docs/optimization_claude_hossouko.md, finding 2).
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        from app.seed import seed_sample_data

        await seed_sample_data()
        token = (await ac.post("/api/token", data={"username": "demo", "password": "demo123"})).json()[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        recorded = await ac.post(
            "/api/merchant/sales",
            json={"amount": "3500", "currency": "XOF", "type": "sale", "idempotency_key": "graphql-sale-001"},
            headers=headers,
        )
        assert recorded.status_code == 201, recorded.text

        response = await ac.post(
            "/graphql",
            headers=headers,
            json={"query": "{ mySales(limit: 5) { source amount currency venueId } }"},
        )
        assert response.status_code == 200, response.text
        sales = response.json()["data"]["mySales"]
        mine = [s for s in sales if s["amount"].startswith("3500")]
        assert mine, sales
        assert mine[0]["source"] == "cash_declared"
        assert mine[0]["venueId"] is not None


@pytest.mark.asyncio
async def test_graphql_my_sales_requires_authentication():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/graphql", json={"query": "{ mySales { source } }"})
        assert response.status_code == 200
        assert "Authentication required" in response.text
