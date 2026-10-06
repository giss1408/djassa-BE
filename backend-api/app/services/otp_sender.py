"""Delivers sign-in codes. The only part of phone sign-in that costs money.

Chosen with `OTP_SENDER`:

* `console` (default outside production): writes the code to the server log
  and, when `OTP_DEV_ECHO=1`, returns it in the API response so the apps can
  be driven locally without a phone. Refused when `HOSSOUKO_ENV=production`: a
  code in a log line is a code anyone with log access can use.
* `africastalking`: SMS through Africa's Talking, which covers Côte d'Ivoire
  and most of West Africa. Needs `AT_USERNAME`, `AT_API_KEY`, and optionally
  `AT_SENDER_ID` (an approved alphanumeric sender) and `AT_SANDBOX=1`.

Another provider (Twilio, a WhatsApp Business template, an operator's own
API) is one more class with a `send` method; nothing else changes.
"""

import logging
import os

import httpx

from ..core.phone import mask_phone

log = logging.getLogger("hossouko.otp")


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


def get_sender():
    name = os.getenv("OTP_SENDER", "console")
    if name == "console":
        if os.getenv("HOSSOUKO_ENV") == "production":
            raise RuntimeError("OTP_SENDER=console is refused when HOSSOUKO_ENV=production")
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
        and os.getenv("HOSSOUKO_ENV") != "production"
    )
