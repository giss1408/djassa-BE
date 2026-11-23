"""Delivers sign-in codes. The only part of phone sign-in that costs money.

Chosen with `OTP_SENDER`:

* `console` (default outside production): writes the code to the server log
  and, when `OTP_DEV_ECHO=1`, returns it in the API response so the apps can
  be driven locally without a phone. Refused when `FIDELIA_ENV=production`: a
  code in a log line is a code anyone with log access can use.
* `orange`: Orange's SMS API for Côte d'Ivoire (developer.orange.com, SMS CI),
  the operator's own route and the cheapest per code. Needs
  `ORANGE_CLIENT_ID` and `ORANGE_CLIENT_SECRET` (My Apps → the app), and
  optionally `ORANGE_SENDER_NAME` once Orange has confirmed it by email
  (at most 11 letters or digits; without it Orange uses its default sender).
  Codes are paid from the prepaid bundle bought in My Apps.
* `africastalking`: SMS through Africa's Talking, which covers Côte d'Ivoire
  and most of West Africa. Needs `AT_USERNAME`, `AT_API_KEY`, and optionally
  `AT_SENDER_ID` (an approved alphanumeric sender) and `AT_SANDBOX=1`.

Several names separated by commas (`orange,africastalking`) are tried in
that order: the next provider sends the code when one fails (an empty
bundle, an outage, a refusal). Orange itself notes delivery issues towards
MTN numbers, so production keeps a second provider behind it.

Another provider (Twilio, a WhatsApp Business template) is one more class
with a `send` method; nothing else changes.
"""

import asyncio
import base64
import logging
import os
import re
import time

import httpx

from ..core.phone import mask_phone

log = logging.getLogger("fidelia.otp")


class OtpDeliveryFailed(RuntimeError):
    pass


class ConsoleSender:
    name = "console"

    async def send(self, phone_e164: str, message: str) -> None:
        # The full number stays out of the log; the code is the point here.
        log.warning("OTP for %s: %s", mask_phone(phone_e164), message)


class AfricasTalkingSender:
    name = "africastalking"

    def __init__(self, username: str, api_key: str, sender_id: str | None, sandbox: bool):
        self._username = username
        self._api_key = api_key
        self._sender_id = sender_id
        host = "api.sandbox.africastalking.com" if sandbox else "api.africastalking.com"
        self._url = f"https://{host}/version1/messaging"

    async def send(self, phone_e164: str, message: str) -> None:
        data = {"username": self._username, "to": phone_e164, "message": message}
        if self._sender_id:
            data["from"] = self._sender_id
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._url, data=data, headers={"apiKey": self._api_key, "Accept": "application/json"}
                )
        except httpx.HTTPError as exc:
            raise OtpDeliveryFailed("SMS provider unreachable") from exc
        if response.status_code >= 300:
            raise OtpDeliveryFailed(f"SMS provider answered {response.status_code}")
        recipients = (response.json().get("SMSMessageData") or {}).get("Recipients") or []
        if not recipients or recipients[0].get("status") != "Success":
            raise OtpDeliveryFailed("SMS provider refused the message")


ORANGE_API = "https://api.orange.com"
# Côte d'Ivoire's sender number on Orange's platform (the "country sender
# number" of the SMS CI API), the same for every app.
ORANGE_CI_SENDER = "2250000"
_SENDER_NAME = re.compile(r"[A-Za-z0-9]{1,11}")

# client_id -> (access token, monotonic time it stops being used). An Orange
# token lasts an hour; get_sender() builds a sender per request, so the token
# lives here, shared by every request of the process.
_orange_tokens: dict[str, tuple[str, float]] = {}
_orange_token_lock = asyncio.Lock()


class OrangeSender:
    name = "orange"

    def __init__(self, client_id: str, client_secret: str, sender_name: str | None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self._client_id = client_id
        self._basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._sender_name = sender_name
        self._transport = transport  # tests only

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=ORANGE_API, timeout=10, transport=self._transport)

    async def _token(self, client: httpx.AsyncClient, renew: bool = False) -> str:
        async with _orange_token_lock:
            cached = _orange_tokens.get(self._client_id)
            if cached and not renew and cached[1] > time.monotonic():
                return cached[0]
            response = await client.post(
                "/oauth/v3/token",
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {self._basic}", "Accept": "application/json"},
            )
            if response.status_code != 200:
                raise OtpDeliveryFailed(f"Orange refused the token request ({response.status_code})")
            body = response.json()
            # Renewed a minute early, so a token never expires mid-request.
            lifetime = int(body.get("expires_in") or 3600) - 60
            _orange_tokens[self._client_id] = (body["access_token"], time.monotonic() + max(lifetime, 0))
            return body["access_token"]

    async def send(self, phone_e164: str, message: str) -> None:
        request = {
            "address": f"tel:{phone_e164}",
            "senderAddress": f"tel:+{ORANGE_CI_SENDER}",
            "outboundSMSTextMessage": {"message": message},
        }
        if self._sender_name:
            request["senderName"] = self._sender_name
        url = f"/smsmessaging/v1/outbound/tel%3A%2B{ORANGE_CI_SENDER}/requests"
        try:
            async with self._client() as client:
                token = await self._token(client)
                response = await client.post(url, json={"outboundSMSMessageRequest": request},
                                             headers={"Authorization": f"Bearer {token}"})
                if response.status_code == 401:  # expired or revoked: one new token, one retry
                    token = await self._token(client, renew=True)
                    response = await client.post(url, json={"outboundSMSMessageRequest": request},
                                                 headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            raise OtpDeliveryFailed("Orange SMS API unreachable") from exc
        if response.status_code != 201:
            # 400: sender name not whitelisted; 403: bundle empty or expired.
            # The reason goes to the log, never the number.
            log.error("Orange SMS refused (%s): %s", response.status_code, _orange_reason(response))
            raise OtpDeliveryFailed(f"Orange SMS API answered {response.status_code}")


def _orange_reason(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "no details"
    error = body.get("requestError") or {}
    exception = error.get("serviceException") or error.get("policyException") or {}
    return str(exception.get("text") or body.get("message") or "no details")[:200]


class FallbackSender:
    """Tries each provider in order until one accepts the code."""

    def __init__(self, senders: list):
        self.senders = senders
        self.name = ",".join(s.name for s in senders)

    async def send(self, phone_e164: str, message: str) -> None:
        from ..metrics import OTP_SMS

        for i, sender in enumerate(self.senders):
            try:
                await sender.send(phone_e164, message)
                OTP_SMS.labels(provider=sender.name, result="sent").inc()
                return
            except OtpDeliveryFailed as exc:
                OTP_SMS.labels(provider=sender.name, result="failed").inc()
                if i == len(self.senders) - 1:
                    raise
                log.warning("OTP via %s failed (%s); trying %s", sender.name, exc, self.senders[i + 1].name)


def get_sender():
    names = [n.strip() for n in os.getenv("OTP_SENDER", "console").split(",") if n.strip()]
    senders = [_one_sender(n) for n in names] or [_one_sender("console")]
    return senders[0] if len(senders) == 1 else FallbackSender(senders)


def _one_sender(name: str):
    if name == "orange":
        client_id, secret = os.getenv("ORANGE_CLIENT_ID"), os.getenv("ORANGE_CLIENT_SECRET")
        if not client_id or not secret:
            raise RuntimeError("OTP_SENDER=orange needs ORANGE_CLIENT_ID and ORANGE_CLIENT_SECRET")
        sender_name = os.getenv("ORANGE_SENDER_NAME") or None
        if sender_name and not _SENDER_NAME.fullmatch(sender_name):
            raise RuntimeError("ORANGE_SENDER_NAME: at most 11 letters or digits, no spaces or accents")
        return OrangeSender(client_id, secret, sender_name)
    if name == "console":
        if os.getenv("FIDELIA_ENV") == "production":
            raise RuntimeError("OTP_SENDER=console is refused when FIDELIA_ENV=production")
        return ConsoleSender()
    if name == "africastalking":
        username, api_key = os.getenv("AT_USERNAME"), os.getenv("AT_API_KEY")
        if not username or not api_key:
            raise RuntimeError("OTP_SENDER=africastalking needs AT_USERNAME and AT_API_KEY")
        return AfricasTalkingSender(
            username, api_key, os.getenv("AT_SENDER_ID") or None, os.getenv("AT_SANDBOX") == "1"
        )
    raise RuntimeError(f"Unknown OTP_SENDER: {name!r}")


def dev_echo_enabled() -> bool:
    """Whether the API may return the code itself. Console sender only."""
    return (
        os.getenv("OTP_DEV_ECHO") == "1"
        and os.getenv("OTP_SENDER", "console") == "console"
        and os.getenv("FIDELIA_ENV") != "production"
    )
