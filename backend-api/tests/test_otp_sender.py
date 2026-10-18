"""Sign-in codes through Orange's SMS API, and falling back to another
provider when one fails (app/services/otp_sender.py). Orange is never called:
its HTTP API is replaced by a recorder that answers like the real one."""

import base64
import json

import httpx
import pytest

from app.services import otp_sender
from app.services.otp_sender import FallbackSender, OrangeSender, OtpDeliveryFailed

PHONE = "+2250701020304"


class FakeOrange:
    """Answers like api.orange.com: a token, then 201 per SMS."""

    def __init__(self, send_statuses=(201,), token_status=200):
        self.send_statuses = list(send_statuses)
        self.token_status = token_status
        self.token_calls: list[httpx.Request] = []
        self.sends: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v3/token":
            self.token_calls.append(request)
            n = len(self.token_calls)
            return httpx.Response(self.token_status, json={
                "token_type": "Bearer", "access_token": f"token-{n}", "expires_in": "3600",
            })
        self.sends.append(request)
        status = self.send_statuses.pop(0) if self.send_statuses else 201
        if status == 401:
            return httpx.Response(401, json={"code": 42, "message": "Expired credentials"})
        if status == 201:
            return httpx.Response(201, json={"outboundSMSMessageRequest": {"resourceURL": "https://api.orange.com/x/abc"}})
        return httpx.Response(status, json={"requestError": {"serviceException": {"text": "Not enough credit"}}})


@pytest.fixture(autouse=True)
def _fresh_token_cache():
    otp_sender._orange_tokens.clear()
    yield
    otp_sender._orange_tokens.clear()


def _sender(fake, sender_name=None):
    return OrangeSender("client-id", "client-secret", sender_name, transport=httpx.MockTransport(fake))


@pytest.mark.asyncio
async def test_orange_gets_a_token_then_sends_from_the_ivorian_sender_number():
    fake = FakeOrange()
    await _sender(fake, sender_name="FIDELIA").send(PHONE, "Fidelia : votre code est 123456.")

    token = fake.token_calls[0]
    assert token.headers["authorization"] == "Basic " + base64.b64encode(b"client-id:client-secret").decode()
    assert token.content == b"grant_type=client_credentials"

    send = fake.sends[0]
    assert send.url.raw_path == b"/smsmessaging/v1/outbound/tel%3A%2B2250000/requests"
    assert send.headers["authorization"] == "Bearer token-1"
    assert json.loads(send.content) == {"outboundSMSMessageRequest": {
        "address": f"tel:{PHONE}",
        "senderAddress": "tel:+2250000",
        "senderName": "FIDELIA",
        "outboundSMSTextMessage": {"message": "Fidelia : votre code est 123456."},
    }}


@pytest.mark.asyncio
async def test_without_an_approved_name_orange_uses_its_default_sender():
    fake = FakeOrange()
    await _sender(fake).send(PHONE, "code")
    assert "senderName" not in json.loads(fake.sends[0].content)["outboundSMSMessageRequest"]


@pytest.mark.asyncio
async def test_one_token_serves_many_codes_across_requests():
    # get_sender() builds a new sender per request; the token outlives it.
    fake = FakeOrange()
    await _sender(fake).send(PHONE, "one")
    await _sender(fake).send(PHONE, "two")
    assert len(fake.token_calls) == 1 and len(fake.sends) == 2


@pytest.mark.asyncio
async def test_an_expired_token_is_renewed_and_the_code_sent_once_more():
    fake = FakeOrange(send_statuses=[401, 201])
    await _sender(fake).send(PHONE, "code")
    assert len(fake.token_calls) == 2
    assert fake.sends[1].headers["authorization"] == "Bearer token-2"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 403, 500])
async def test_a_refused_message_is_a_delivery_failure_without_the_number(status):
    with pytest.raises(OtpDeliveryFailed) as failure:
        await _sender(FakeOrange(send_statuses=[status])).send(PHONE, "code")
    assert str(status) in str(failure.value)
    assert PHONE not in str(failure.value) and "0701020304" not in str(failure.value)


@pytest.mark.asyncio
async def test_bad_credentials_are_a_delivery_failure():
    with pytest.raises(OtpDeliveryFailed, match="token"):
        await _sender(FakeOrange(token_status=401)).send(PHONE, "code")


@pytest.mark.asyncio
async def test_orange_unreachable_is_a_delivery_failure():
    def down(_request):
        raise httpx.ConnectError("no route")

    with pytest.raises(OtpDeliveryFailed, match="unreachable"):
        await _sender(down).send(PHONE, "code")


class Recorder:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.sent = name, fail, []

    async def send(self, phone, message):
        self.sent.append(phone)
        if self.fail:
            raise OtpDeliveryFailed(f"{self.name} refused")


@pytest.mark.asyncio
async def test_the_next_provider_sends_when_the_first_fails():
    first, second = Recorder("orange", fail=True), Recorder("africastalking")
    await FallbackSender([first, second]).send(PHONE, "code")
    assert first.sent == [PHONE] and second.sent == [PHONE]


@pytest.mark.asyncio
async def test_the_second_provider_is_not_used_when_the_first_works():
    first, second = Recorder("orange"), Recorder("africastalking")
    await FallbackSender([first, second]).send(PHONE, "code")
    assert second.sent == []


@pytest.mark.asyncio
async def test_when_every_provider_fails_the_code_is_not_sent():
    with pytest.raises(OtpDeliveryFailed):
        await FallbackSender([Recorder("orange", fail=True), Recorder("africastalking", fail=True)]).send(PHONE, "code")


def test_orange_needs_its_credentials(monkeypatch):
    monkeypatch.setenv("OTP_SENDER", "orange")
    monkeypatch.delenv("ORANGE_CLIENT_ID", raising=False)
    monkeypatch.delenv("ORANGE_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="ORANGE_CLIENT_ID"):
        otp_sender.get_sender()


def test_a_list_of_providers_builds_a_fallback_chain(monkeypatch):
    monkeypatch.setenv("OTP_SENDER", "orange,africastalking")
    monkeypatch.setenv("ORANGE_CLIENT_ID", "id")
    monkeypatch.setenv("ORANGE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("AT_USERNAME", "fidelia")
    monkeypatch.setenv("AT_API_KEY", "key")
    sender = otp_sender.get_sender()
    assert isinstance(sender, FallbackSender)
    assert [s.name for s in sender.senders] == ["orange", "africastalking"]


@pytest.mark.parametrize("name", ["FIDELIA PRO", "Fidélia", "FIDELIA-CODES"])
def test_a_sender_name_orange_would_refuse_stops_the_start(monkeypatch, name):
    monkeypatch.setenv("OTP_SENDER", "orange")
    monkeypatch.setenv("ORANGE_CLIENT_ID", "id")
    monkeypatch.setenv("ORANGE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ORANGE_SENDER_NAME", name)
    with pytest.raises(RuntimeError, match="ORANGE_SENDER_NAME"):
        otp_sender.get_sender()


def test_the_console_sender_stays_refused_in_production_even_in_a_chain(monkeypatch):
    monkeypatch.setenv("FIDELIA_ENV", "production")
    monkeypatch.setenv("OTP_SENDER", "orange,console")
    monkeypatch.setenv("ORANGE_CLIENT_ID", "id")
    monkeypatch.setenv("ORANGE_CLIENT_SECRET", "secret")
    with pytest.raises(RuntimeError, match="console"):
        otp_sender.get_sender()


@pytest.mark.asyncio
async def test_each_provider_attempt_is_counted():
    from app.metrics import OTP_SMS

    def value(provider, result):
        return OTP_SMS.labels(provider=provider, result=result)._value.get()

    before = (value("orange", "failed"), value("africastalking", "sent"))
    await FallbackSender([Recorder("orange", fail=True), Recorder("africastalking")]).send(PHONE, "code")
    assert value("orange", "failed") == before[0] + 1
    assert value("africastalking", "sent") == before[1] + 1


def test_a_bad_sender_setting_stops_the_api_start(monkeypatch):
    import asyncio

    from app.main import startup

    monkeypatch.setenv("OTP_SENDER", "orange")
    monkeypatch.delenv("ORANGE_CLIENT_ID", raising=False)
    with pytest.raises(RuntimeError, match="ORANGE_CLIENT_ID"):
        asyncio.run(startup())
