import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_tier_zero_identity_profile_and_provider_gated_upgrade():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_response = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        token = token_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = await ac.post(
            "/api/identity/profile",
            headers=headers,
            json={
                "country_code": "CI",
                "phone_e164": "+2250700000000",
                "operator": "wave_ci",
                "consent_version": "identity-v1",
            },
        )
        assert created.status_code == 201
        assert created.json()["verification_tier"] == 0
        assert created.json()["verification_provider"] is None

        request = await ac.post("/api/identity/verification/1", headers=headers)
        assert request.status_code == 200
        assert request.json()["status"] == "provider_required"


@pytest.mark.asyncio
async def test_identity_rejects_country_phone_mismatch():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_response = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        token = token_response.json()["access_token"]
        response = await ac.post(
            "/api/identity/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "country_code": "CI",
                "phone_e164": "+233201234567",
                "operator": "mtn_momo_gh",
                "consent_version": "identity-v1",
            },
        )
        assert response.status_code == 422