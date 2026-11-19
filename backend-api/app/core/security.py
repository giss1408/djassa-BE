import os
from datetime import datetime, timedelta
from typing import Optional

from passlib.context import CryptContext
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from . import sso

SECRET_KEY = os.getenv("FIDELIA_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("FIDELIA_SECRET_KEY must be set before starting the application")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")
# Same scheme, but a missing token is not an error: for the public catalogue.
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/token", auto_error=False)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    if payload is None:
        # Not one of fidelia's own tokens: a platform `auth` token is accepted when SSO is switched on (core/sso.py).
        sso_user = sso.user_from_token(token)
        if sso_user is not None:
            return sso_user
    subject = payload.get("sub") if payload else None
    if not subject or not isinstance(subject, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    if "role" not in payload and os.getenv("FIDELIA_REJECT_ROLELESS") == "1":
        # A token without a role used to be a merchant token. After the SSO cutover nothing legitimate lacks a role.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    # Tokens issued before roles existed carry none; they were merchant tokens.
    return {"username": subject, "role": payload.get("role", "merchant")}


async def get_optional_user(token: str | None = Depends(oauth2_optional)):
    """The caller, or None for someone browsing without an account.

    The customer app shows offers, shops and on-duty pharmacies before any
    sign-in; only paying and points need one. A token that is present but
    invalid is still a 401, so the app renews it instead of silently
    showing the anonymous view to a signed-in customer."""
    if not token:
        return None
    return await get_current_user(token)


# Fidelia Pro sessions: the shop owner, and the cashiers the owner added.
# Routes a cashier may use take `require_role(*SHOP_STAFF)`; owner-only routes
# (money settings, deals, photos, location, statements, staff) keep "merchant".
SHOP_STAFF = ("merchant", "cashier")


def require_role(*roles: str):
    """Dependency factory: 403 unless the caller's token carries one of `roles`."""

    async def checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for this account")
        return user

    return checker


def require_step_up(max_age_seconds: int = 300):
    """Route dependency for sensitive actions (wallet, staff, exports, role changes). For `auth` sign-ins only: the user must have
    re-proved a factor within `max_age_seconds` (password for shop staff, authenticator code for admins: `POST /v1/step-up` at
    auth gives a fresh token) AND the session must still be alive at auth. fidelia's own legacy tokens are unchanged."""

    async def checker(user=Depends(get_current_user)):
        if not user.get("sso"):
            return user
        from regisse_kit.sso import SsoError

        try:
            user["principal"].require_step_up(max_age_seconds, amr="totp" if user["role"] == "admin" else "pwd")
        except SsoError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="step_up_required") from None
        alive = await sso.session_alive(user["token"])
        if alive is None and os.getenv("FIDELIA_SSO_MONEY_FAIL_CLOSED", "1") != "0":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="sso_unavailable")
        if alive is False:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sso_session_ended")
        return user

    return checker


# The default (5 minutes), shared by the routes that ask for a fresh proof.
step_up = require_step_up()
