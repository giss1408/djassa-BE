"""One-time sign-in codes and refresh tokens: generation and hashing.

Codes are 6 digits, live 5 minutes, and allow 5 guesses: 5 in a million per
code, with sends capped per number and per IP. Only HMACs are stored, keyed on
the app secret, so a database dump yields neither usable codes nor tokens.
"""

import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from .security import SECRET_KEY

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=5)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=60)
# A number receives at most this many codes per hour. SMS pumping fraud
# (someone triggering sends to premium numbers) is the main cost risk.
MAX_SENDS_PER_HOUR = 5
# All numbers together receive at most this many codes in 24 hours
# (`OTP_DAILY_SMS_BUDGET`). The caps above stop one number or one IP; this
# stops an attack that rotates both, at a cost known in advance. Past it, sign
# in waits for the window to roll over and the OtpDailyBudgetReached alert
# fires. Size it from real traffic: a few times a normal day.
DEFAULT_DAILY_SMS_BUDGET = 500


def daily_sms_budget() -> int:
    return int(os.getenv("OTP_DAILY_SMS_BUDGET", DEFAULT_DAILY_SMS_BUDGET))

REFRESH_TTL = timedelta(days=90)


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(phone_e164: str, code: str) -> str:
    # Bound to the number, so a code hash cannot be replayed for another one.
    return hmac.new(SECRET_KEY.encode(), f"otp:{phone_e164}:{code}".encode(), hashlib.sha256).hexdigest()


def code_matches(phone_e164: str, code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_code(phone_e164, code), stored_hash)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_family() -> str:
    return secrets.token_hex(16)
