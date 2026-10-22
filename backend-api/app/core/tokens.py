"""Refresh tokens and account-check secrets: generation and hashing.

Only hashes are stored, so a database dump yields neither usable tokens nor
usable codes or temporary passwords.
"""

import hashlib
import hmac
import secrets

from .security import SECRET_KEY


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_family() -> str:
    return secrets.token_hex(16)


def hmac_secret(user_id: int, kind: str, secret: str) -> str:
    # Bound to the user and the kind of check, so a hash cannot be replayed
    # for another account or another purpose.
    return hmac.new(SECRET_KEY.encode(), f"check:{user_id}:{kind}:{secret}".encode(), hashlib.sha256).hexdigest()


def secret_matches(user_id: int, kind: str, secret: str, stored: str) -> bool:
    return hmac.compare_digest(hmac_secret(user_id, kind, secret), stored)
