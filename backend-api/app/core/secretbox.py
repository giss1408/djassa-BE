"""Encrypt merchants' third-party secrets at rest (e.g. their Wave API key).

A merchant who connects their Wave Business account hands Hossouko a key that
can create payments into their wallet. It is stored encrypted with Fernet
(AES-128-CBC + HMAC-SHA256), under HOSSOUKO_ENCRYPTION_KEY, so a database dump
alone does not reveal it. Decryption happens only at the moment of a call.

HOSSOUKO_ENCRYPTION_KEY: any long random string (Render can generate it). In
production it is mandatory. Elsewhere it falls back to a key derived from
HOSSOUKO_SECRET_KEY so development and tests need no extra setup. Changing the
key makes existing secrets unreadable: merchants would have to reconnect.
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


class SecretUnavailable(RuntimeError):
    """The stored secret cannot be decrypted (wrong or rotated key)."""


def _fernet() -> Fernet:
    material = os.getenv("HOSSOUKO_ENCRYPTION_KEY")
    if not material:
        if os.getenv("HOSSOUKO_ENV") == "production":
            raise RuntimeError("HOSSOUKO_ENCRYPTION_KEY must be set in production")
        material = "dev-only:" + (os.getenv("HOSSOUKO_SECRET_KEY") or "")
    # Fernet wants 32 url-safe base64 bytes; derive them from any string.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


def seal(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def unseal(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretUnavailable("stored secret cannot be decrypted with the current key") from exc


def hint(secret: str) -> str:
    """'…a1B2': enough for a merchant to recognise which key is connected."""
    return "…" + secret[-4:] if len(secret) >= 8 else "…"
