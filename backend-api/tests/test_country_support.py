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


@pytest.mark.asyncio
async def test_support_request_alerts_the_team_without_its_text(monkeypatch):
    from app.services import admin_alerts

    monkeypatch.setenv("NTFY_TOPIC", "fidelia-test-topic")
    monkeypatch.setenv("NTFY_URL", "memory")
    admin_alerts.SENT.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token = (await ac.post("/api/token", data={"username": "demo", "password": "demo123"})).json()["access_token"]
        r = await ac.post(
            "/api/support/requests",
            headers={"Authorization": f"Bearer {token}"},
            json={"country_code": "CI", "language": "fr", "channel": "whatsapp", "category": "payment",
                  "message": "Je n'ai pas recu la confirmation."},
        )
    assert r.status_code == 201
    [alert] = admin_alerts.SENT
    assert alert["title"] == "Nouvelle demande de support"
    assert alert["message"] == f"#{r.json()['id']} · payment · CI (whatsapp)"
    assert "confirmation" not in alert["message"]


@pytest.mark.asyncio
async def test_alerts_are_off_without_a_topic(monkeypatch):
    from app.services import admin_alerts

    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.setenv("NTFY_URL", "memory")
    admin_alerts.SENT.clear()
    await admin_alerts.send("t", "m")
    assert admin_alerts.SENT == []
