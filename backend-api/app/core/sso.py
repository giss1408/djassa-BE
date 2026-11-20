"""Sign-in through the platform `auth` service (SSO), next to fidelia's own tokens (dual-accept).

Off unless FIDELIA_SSO_ENABLED=1, so nothing changes until it is switched on:
  FIDELIA_SSO_ENABLED=1
  FIDELIA_SSO_ISSUER=https://auth-api.regisse.com          (the `iss` claim)
  FIDELIA_SSO_JWKS_URL=https://auth-api.regisse.com/.well-known/jwks.json
  FIDELIA_SSO_AUDIENCE=fidelia                              (default)
  FIDELIA_SSO_AUTH_URL=http://auth:8000  FIDELIA_SSO_SERVICE_KEY=...     (online session check on sensitive routes)
  FIDELIA_SSO_MONEY_FAIL_CLOSED=1 (default): when auth cannot be reached, sensitive routes answer 503, never "allowed"

What a verified token gives fidelia: the SAME identity shape as its own tokens ({"username": "tel:+225...", "role": ...}), taken from
the `ph` claim, so every table keyed by the phone key keeps working. The algorithm is pinned to EdDSA by regisse_kit.sso; a
token without a role, for another audience/issuer, or flagged "must change password" is refused. Nothing is created from a token:
a shop is still linked to a phone by fidelia's own enrolment.
"""

import logging
import os
from dataclasses import dataclass

import httpx

# auth role -> fidelia role. `super_admin` is an admin for fidelia.
ROLE_MAP = {"customer": "customer", "merchant": "merchant", "cashier": "cashier", "agent": "agent", "admin": "admin", "super_admin": "admin"}

_verifiers: dict[tuple[str, str, str], object] = {}


def enabled() -> bool:
    return os.getenv("FIDELIA_SSO_ENABLED") == "1" and bool(os.getenv("FIDELIA_SSO_ISSUER")) and bool(os.getenv("FIDELIA_SSO_JWKS_URL"))


def _verifier():
    from regisse_kit.sso import SsoVerifier  # imported here: an image without the kit still runs with SSO off

    issuer, url, aud = os.environ["FIDELIA_SSO_ISSUER"], os.environ["FIDELIA_SSO_JWKS_URL"], os.getenv("FIDELIA_SSO_AUDIENCE", "fidelia")
    key = (issuer, url, aud)
    if key not in _verifiers:
        _verifiers[key] = SsoVerifier(issuer=issuer, audience=aud, jwks_fetch=lambda: httpx.get(url, timeout=5).raise_for_status().json())
    return _verifiers[key]


def reset() -> None:
    _verifiers.clear()


@dataclass
class SsoUser:
    username: str  # tel:+225...
    role: str
    principal: object  # regisse_kit.sso.Principal
    token: str

    def as_dict(self) -> dict:
        return {"username": self.username, "role": self.role, "sso": True, "principal": self.principal, "token": self.token}


def user_from_token(token: str) -> dict | None:
    """fidelia's current-user dict for an `auth` token, or None when the token is not acceptable. Never raises on a bad token."""
    if not enabled():
        return None
    try:
        from regisse_kit.sso import SsoError

        try:
            p = _verifier().verify(token)  # type: ignore[attr-defined]
        except SsoError:
            return None
    except Exception:  # noqa: BLE001: JWKS unreachable, kit missing, anything else: a clean 401, never a 500, and no valid-looking identity
        logging.getLogger("fidelia.sso").warning("SSO token not verified (auth unreachable or misconfigured?)", exc_info=False)
        return None
    role = ROLE_MAP.get(p.role)
    if role is None or p.must_change_password or not p.phone_key.startswith("tel:+"):
        return None
    return SsoUser(username=p.phone_key, role=role, principal=p, token=token).as_dict()


async def session_alive(token: str) -> bool | None:
    """Online check with auth (is this session still alive, is the user still active with this role?). None = auth unreachable."""
    url, key = os.getenv("FIDELIA_SSO_AUTH_URL"), os.getenv("FIDELIA_SSO_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.post(f"{url.rstrip('/')}/v1/introspect", json={"token": token}, headers={"X-Service-Key": key})
        r.raise_for_status()
        return bool(r.json().get("active"))
    except (httpx.HTTPError, ValueError):
        return None


async def erase_identity(phone_e164: str) -> bool | None:
    """After fidelia erased a person's data (her own deletion, or an admin acting on a request), tell auth so her access to fidelia
    ends and her identity is erased when nothing else is left (`POST /v1/service/erase`, idempotent). Best effort, never raises: the
    deletion in fidelia stands either way, and a failure is logged with no phone number so the team can run it again. Off unless SSO is
    on and configured. None = not configured (nothing to do), True = auth answered, False = it could not be reached (retry later)."""
    url, key = os.getenv("FIDELIA_SSO_AUTH_URL"), os.getenv("FIDELIA_SSO_SERVICE_KEY")
    if not enabled() or not url or not key:
        return None
    log = logging.getLogger("fidelia.sso")
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(f"{url.rstrip('/')}/v1/service/erase", json={"phone": phone_e164}, headers={"X-Service-Key": key})
        r.raise_for_status()
        log.info("auth erase: %s", r.json().get("result"))
        return True
    except (httpx.HTTPError, ValueError):
        log.error("auth erase FAILED: the person is deleted in fidelia but her auth identity remains; run the erase again", exc_info=False)
        return False
