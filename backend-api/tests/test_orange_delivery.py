"""Orange's delivery receipts for sign-in codes (app/api/orange_sms.py).

Orange signs nothing, so the URL carries a secret token. A receipt holds the
recipient's number: only its network is kept, as a metric."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.metrics import OTP_SMS_DELIVERY

TOKEN = "d" * 64


def _receipt(address="tel:+2250501020304", status="DeliveredToTerminal"):
    return {"deliveryInfoNotification": {
        "callbackData": "3f1c2a7e-0000-4000-8000-1234567890ab",
        "deliveryInfo": {"address": address, "deliveryStatus": status},
    }}


def _count(network, status):
    return OTP_SMS_DELIVERY.labels(network=network, status=status)._value.get()


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setenv("ORANGE_DR_TOKEN", TOKEN)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_a_receipt_is_counted_by_network_and_status(client):
    before = _count("mtn", "DeliveryImpossible")
    r = await client.post(f"/webhooks/orange/sms-dr/{TOKEN}", json=_receipt(status="DeliveryImpossible"))
    assert r.status_code == 200
    assert _count("mtn", "DeliveryImpossible") == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("address,network", [
    ("tel:+2250701020304", "orange"),
    ("tel:+2250501020304", "mtn"),
    ("tel:+2250101020304", "moov"),
    ("tel:+2250201020304", "other"),
    ("tel:+33612345678", "other"),
])
async def test_the_network_comes_from_the_ivorian_prefix(client, address, network):
    before = _count(network, "DeliveredToTerminal")
    await client.post(f"/webhooks/orange/sms-dr/{TOKEN}", json=_receipt(address=address))
    assert _count(network, "DeliveredToTerminal") == before + 1


@pytest.mark.asyncio
async def test_a_wrong_token_is_not_found(client):
    r = await client.post("/webhooks/orange/sms-dr/" + "x" * 64, json=_receipt())
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_without_a_configured_token_the_endpoint_does_not_exist(client, monkeypatch):
    monkeypatch.delenv("ORANGE_DR_TOKEN")
    assert (await client.post(f"/webhooks/orange/sms-dr/{TOKEN}", json=_receipt())).status_code == 404


@pytest.mark.asyncio
async def test_an_unknown_status_is_counted_without_inventing_a_label(client):
    before = _count("orange", "unknown")
    r = await client.post(f"/webhooks/orange/sms-dr/{TOKEN}",
                          json=_receipt(address="tel:+2250701020304", status="SomethingNew"))
    assert r.status_code == 200
    assert _count("orange", "unknown") == before + 1


@pytest.mark.asyncio
async def test_a_malformed_receipt_is_acknowledged_so_orange_does_not_retry(client):
    r = await client.post(f"/webhooks/orange/sms-dr/{TOKEN}", content=b"not json",
                          headers={"Content-Type": "application/json"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_the_number_never_reaches_the_log(client, caplog):
    caplog.set_level("DEBUG")
    await client.post(f"/webhooks/orange/sms-dr/{TOKEN}", json=_receipt(address="tel:+2250501020304"))
    assert "0501020304" not in caplog.text and "2250501020304" not in caplog.text


def test_a_short_token_stops_the_start(monkeypatch):
    from app.api import orange_sms

    monkeypatch.setenv("ORANGE_DR_TOKEN", "short")
    with pytest.raises(RuntimeError, match="ORANGE_DR_TOKEN"):
        orange_sms.check_settings()
