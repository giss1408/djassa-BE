"""Wave Business API: checkout sessions and webhook signatures.

Option B of the pilot (docs/technical/DEPLOY-TEST.md): each merchant connects
THEIR OWN Wave Business account. Every call below uses that merchant's key,
so the money always lands in the merchant's wallet; Fidelia never holds it.

References (docs.wave.com):
* Checkout: POST /v1/checkout/sessions -> {id, wave_launch_url, ...}; the
  launch URL must be opened in the phone's browser, which hands over to the
  Wave app. GET /v1/checkout/sessions/:id reads a session back.
* Webhooks: header `Wave-Signature: t=<unix>,v1=<hex>`; v1 is
  HMAC-SHA256(secret, f"{t}{raw_body}") in hex. Several v1 values may be sent
  during a secret rotation; any match is enough.

Wave documents no sandbox: tests use recorded shapes with a mock transport, and
the first live check is a small real payment.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

WAVE_API = "https://api.wave.com"
# Recommended by Wave: refuse webhook deliveries older than five minutes.
REPLAY_TOLERANCE_S = 300


class WaveError(RuntimeError):
    """Wave refused or failed a call. `message` is safe to show."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    launch_url: str | None
    checkout_status: str  # open | complete | expired
    payment_status: str | None  # processing | cancelled | succeeded
    transaction_id: str | None
    amount: int | None
    client_reference: str | None

    @property
    def succeeded(self) -> bool:
        return self.payment_status == "succeeded"

    @property
    def failed(self) -> bool:
        # A closed session that did not succeed will never be paid.
        return self.checkout_status in ("complete", "expired") and not self.succeeded


def parse_amount(value) -> int | None:
    """Wave sends amounts as decimal strings ("2500", "2500.00"). XOF has no
    minor unit; anything with a fractional franc is rejected, not rounded."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return int(d) if d == d.to_integral_value() and d > 0 else None


def _session(data: dict) -> CheckoutSession:
    return CheckoutSession(
        id=data["id"],
        launch_url=data.get("wave_launch_url"),
        checkout_status=data.get("checkout_status", "open"),
        payment_status=data.get("payment_status"),
        transaction_id=data.get("transaction_id"),
        amount=parse_amount(data.get("amount")),
        client_reference=data.get("client_reference"),
    )


class WaveClient:
    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 15.0):
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(
            base_url=WAVE_API,
            transport=self._transport,
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._api_key}"},
        ) as client:
            try:
                r = await client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise WaveError("Wave ne repond pas. Reessayez dans un instant.") from exc
        if r.status_code in (401, 403):
            raise WaveError("La cle Wave du commercant est refusee (revoquee ou sans acces Checkout).", r.status_code)
        if r.status_code >= 400:
            try:
                detail = r.json().get("message") or r.json().get("code")
            except ValueError:
                detail = None
            raise WaveError(f"Wave a refuse le paiement{': ' + detail if detail else ''}.", r.status_code)
        return r.json()

    async def create_checkout(
        self,
        *,
        amount: int,
        currency: str,
        client_reference: str,
        success_url: str,
        error_url: str,
        restrict_payer_mobile: str | None = None,
    ) -> CheckoutSession:
        body = {
            "amount": str(amount),
            "currency": currency,
            "client_reference": client_reference,
            "success_url": success_url,
            "error_url": error_url,
        }
        if restrict_payer_mobile:
            # Only the wallet the customer named can pay this session.
            body["restrict_payer_mobile"] = restrict_payer_mobile
        return _session(await self._request("POST", "/v1/checkout/sessions", json=body))

    async def get_checkout(self, session_id: str) -> CheckoutSession:
        return _session(await self._request("GET", f"/v1/checkout/sessions/{session_id}"))

    async def check_key(self) -> None:
        """Raise WaveError unless the key is live and has Checkout access.
        A search moves no money, which makes it the safe probe at connection."""
        await self._request(
            "GET", "/v1/checkout/sessions/search", params={"client_reference": "fidelia-key-check"}
        )


def verify_signature(secret: str, header: str | None, body: bytes, *, now: float | None = None) -> bool:
    """Check a `Wave-Signature` header against the raw request body."""
    if not header or not secret:
        return False
    timestamp = None
    signatures = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not timestamp or not signatures or not timestamp.isdigit():
        return False
    if abs((now if now is not None else time.time()) - int(timestamp)) > REPLAY_TOLERANCE_S:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in signatures)


def sign(secret: str, body: bytes, timestamp: int) -> str:
    """Build a `Wave-Signature` header value (tests and local tooling)."""
    mac = hmac.new(secret.encode(), str(timestamp).encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def client_for(api_key: str) -> WaveClient:
    """Every Wave call goes through here, so tests can swap the transport."""
    return WaveClient(api_key)
