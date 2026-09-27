import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_country_configuration_and_localized_support():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        countries = await ac.get("/api/config/countries")
        assert countries.status_code == 200
        assert {country["code"] for country in countries.json()["countries"]} >= {"CI", "GH", "NG", "KE"}

        token_response = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        token = token_response.json()["access_token"]
        response = await ac.post(
            "/api/support/requests",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "country_code": "CI",
                "language": "fr",
                "channel": "whatsapp",
                "category": "payment",
                "message": "Je n'ai pas recu la confirmation.",
            },
        )
        assert response.status_code == 201
        assert response.json()["confirmation"] == "Votre demande d'assistance a bien ete recue."


@pytest.mark.asyncio
async def test_support_rejects_unavailable_language():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_response = await ac.post("/api/token", data={"username": "demo", "password": "demo123"})
        token = token_response.json()["access_token"]
        response = await ac.post(
            "/api/support/requests",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "country_code": "KE",
                "language": "fr",
                "channel": "whatsapp",
                "category": "account",
                "message": "Help",
            },
        )
        assert response.status_code == 422
