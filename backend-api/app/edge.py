"""The API behind Cloudflare and Render's proxy: who is calling, and whether
the request really came through Cloudflare.

**Which address a request counts against** (rate limits, the investor brief's
log line). Never the first `X-Forwarded-For` entry: the caller writes that
one, and uvicorn's `--forwarded-allow-ips '*'` trusts it, so a fresh made-up
address per request would mean a fresh rate limit per request, and unlimited
sign-in SMS. Instead:

* With `CLOUDFLARE_ORIGIN_SECRET` set and the request carrying it:
  `CF-Connecting-IP`, which Cloudflare sets itself and overwrites if a caller
  sends one.
* Otherwise: the last `X-Forwarded-For` entry, the one Render's proxy appended
  (the peer it saw), or the socket's peer when there is no proxy (local runs).

**The origin secret.** The onrender.com address stays reachable after the
domain moves to Cloudflare, so anyone could call it directly with their own
`CF-Connecting-IP` and skip the WAF. A Cloudflare Transform Rule adds
`X-Origin-Auth: <secret>` to every request it forwards; with
`CLOUDFLARE_ORIGIN_SECRET` set, the API answers 403 to any request without it.
Two values separated by a comma (`new,old`) are both accepted while rotating.
`/health` (Render's own check) and `/metrics` (scraped over the private
network, behind its own token) are exempt.

Production refuses to start without the origin secret, and without
`RATE_LIMIT_STORAGE_URI`: in-memory counters reset on every deploy and are
per instance, so two instances would double every limit.
"""

import hmac
import os

from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

ORIGIN_HEADER = "x-origin-auth"
EXEMPT_PATHS = frozenset({"/health", "/metrics"})
MIN_SECRET_LENGTH = 32


def _secrets() -> list[str]:
    return [s.strip() for s in os.getenv("CLOUDFLARE_ORIGIN_SECRET", "").split(",") if s.strip()]


def _carries_secret(value: str | None, secrets: list[str]) -> bool:
    if not value:
        return False
    # Compare against every value, no early exit: the time taken says nothing
    # about which one was close.
    return any([hmac.compare_digest(value.encode(), s.encode()) for s in secrets])


def via_cloudflare(request: Request) -> bool:
    secrets = _secrets()
    return bool(secrets) and _carries_secret(request.headers.get(ORIGIN_HEADER), secrets)


def client_ip(request: Request) -> str:
    if via_cloudflare(request):
        cf = request.headers.get("cf-connecting-ip", "").strip()
        if cf:
            return cf
    forwarded = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if forwarded:
        return forwarded[-1]
    return request.client.host if request.client else "unknown"


def check_settings() -> None:
    """Called at startup: a bad setting stops the start, not every request."""
    secrets = _secrets()
    if any(len(s) < MIN_SECRET_LENGTH for s in secrets):
        raise RuntimeError(f"CLOUDFLARE_ORIGIN_SECRET: each value needs at least {MIN_SECRET_LENGTH} characters")
    if os.getenv("FIDELIA_ENV") == "production":
        if not secrets:
            raise RuntimeError("FIDELIA_ENV=production needs CLOUDFLARE_ORIGIN_SECRET (the API is served through Cloudflare)")
        if not os.getenv("RATE_LIMIT_STORAGE_URI"):
            raise RuntimeError("FIDELIA_ENV=production needs RATE_LIMIT_STORAGE_URI (shared rate-limit counters)")


class OriginGate:
    """Outermost middleware: a refused request costs no rate-limit slot."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") not in EXEMPT_PATHS:
            secrets = _secrets()
            if secrets:
                value = dict(scope.get("headers") or []).get(ORIGIN_HEADER.encode())
                if not _carries_secret(value.decode("latin-1") if value else None, secrets):
                    await PlainTextResponse("Forbidden", status_code=403)(scope, receive, send)
                    return
        await self.app(scope, receive, send)
