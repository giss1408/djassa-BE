import os
from datetime import datetime, timedelta
from typing import Optional

from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("FIDELIA_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("FIDELIA_SECRET_KEY must be set before starting the application")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# Same scheme, but a missing token is not an error: for the public catalogue.
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


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
    except JWTError:
        return None


def session_from_payload(payload: dict | None) -> dict | None:
    """The session a decoded token describes, or None without a usable subject.
    The one place that reads `vf` and `pc`; code that decodes a token itself
    must go through here and check `is_held`."""
    subject = payload.get("sub") if payload else None
    if not subject or not isinstance(subject, str):
        return None
    # Tokens issued before roles existed carry none; they were merchant tokens.
    # Tokens issued before password sign-in carry no `vf`: they came from SMS,
    # which proved the number.
    return {
        "username": subject,
        "role": payload.get("role", "merchant"),
        "verified": bool(payload.get("vf", True)),
        "must_change_password": bool(payload.get("pc", False)),
    }


def is_held(session: dict) -> bool:
    return not session["verified"] or session["must_change_password"]


async def get_session_user(token: str = Depends(oauth2_scheme)):
    """Any valid session, including one still held back: a number not yet
    proven (`vf` false) or a temporary password to replace (`pc` true).
    Only the few routes that finish those steps use this."""
    session = session_from_payload(decode_access_token(token))
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return session


async def get_current_user(user=Depends(get_session_user)):
    """A fully signed-in caller: number proven and no password change owed."""
    if not user["verified"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="number_not_verified")
    if user["must_change_password"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password_change_required")
    return user


async def get_optional_user(token: str | None = Depends(oauth2_optional)):
    """The caller, or None for someone browsing without an account.

    The customer app shows offers, shops and on-duty pharmacies before any
    sign-in; only paying and points need one. A token that is present but
    invalid is still a 401, so the app renews it instead of silently
    showing the anonymous view to a signed-in customer. A session still held
    back (number unproven, password to change) browses as anonymous."""
    if not token:
        return None
    user = await get_session_user(token)
    return None if is_held(user) else user


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
