"""Sign-in.

Phone + one-time code is the real path (CONCEPT.md, Tier 0: the customer is
recognised by phone number). The token subject is `phone_key(e164)`, the key
counter loyalty already uses, so a customer's counter points follow them into
the app the moment they prove they hold the number.

    POST /api/auth/otp/request   {phone, app}         -> code sent
    POST /api/auth/otp/verify    {phone, code, app}   -> access + refresh token
    POST /api/auth/refresh       {refresh_token}      -> rotated pair
    POST /api/auth/logout        {refresh_token}      -> session revoked
    GET  /api/auth/me
    POST /api/admin/users/roles  (admin) grant merchant/admin, link a venue

`app` is "customer" or "merchant". Anyone can open a customer session; a
merchant session needs the merchant role, which only an admin grants.

`POST /api/token` (username/password demo accounts) stays for local
development and the test suite, and answers 404 when DJASSA_ENV=production.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core import otp, security
from ..core.phone import InvalidPhone, mask_phone, normalize_phone, phone_key
from ..db import get_db
from ..metrics import AUTH_EVENTS
from ..rate_limiter import limiter
from ..services.otp_sender import OtpDeliveryFailed, dev_echo_enabled, get_sender

router = APIRouter()

ACCESS_TTL = timedelta(minutes=60)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Demo accounts (development and tests only) -----------------------------

# The role travels in the token so the customer app, the merchant app and admin
# tools share one login endpoint without seeing each other's routes.
_DEMO_USERS = {
    "demo": {"hashed_password": security.get_password_hash("demo123"), "role": "merchant"},
    "client": {"hashed_password": security.get_password_hash("client123"), "role": "customer"},
    "admin": {"hashed_password": security.get_password_hash("admin123"), "role": "admin"},
}


def demo_login_enabled() -> bool:
    return os.getenv("DJASSA_ENV") != "production" and os.getenv("DJASSA_DEMO_LOGIN", "1") != "0"


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    if not demo_login_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    user = _DEMO_USERS.get(form_data.username)
    if not user or not security.verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token = security.create_access_token({"sub": form_data.username, "role": user["role"]})
    return {"access_token": access_token, "token_type": "bearer", "role": user["role"]}


# --- Shared test numbers (DJASSA_ENV=test only) ------------------------------

# TEST_OTP_NUMBERS="+2250700000001:000000,+2250700000002:000000": these numbers
# sign in with their fixed code, so testers share an account the way they
# shared demo/demo123. Nothing is stored or sent for them, so the per-number
# cooldown and hourly cap (which bound SMS spend) do not apply, and one
# tester's request never voids another's code. Sign-in only: recovery and
# number changes on these numbers still go through real codes.


def test_numbers() -> dict[str, str]:
    raw = os.getenv("TEST_OTP_NUMBERS", "").strip()
    if not raw:
        return {}
    env = os.getenv("DJASSA_ENV")
    if env == "production":
        raise RuntimeError("TEST_OTP_NUMBERS is refused when DJASSA_ENV=production")
    if env != "test":
        return {}
    numbers = {}
    for entry in raw.split(","):
        phone, _, code = entry.strip().partition(":")
        if not phone:
            continue
        if not (len(code) == otp.CODE_LENGTH and code.isdigit()):
            raise RuntimeError(f"TEST_OTP_NUMBERS: {phone} needs a {otp.CODE_LENGTH}-digit code after ':'")
        numbers[normalize_phone(phone, "CI")] = code
    return numbers


# --- Phone + one-time code ---------------------------------------------------

AppName = Literal["customer", "merchant", "admin"]

# The session each app opens, best first: Djassa Pro opens an owner's session
# for an owner and a cashier's for a cashier, djassa-installer an admin's or a
# field agent's. Customer sessions need no grant.
_APP_ROLES = {
    "customer": ("customer",),
    "merchant": ("merchant", "cashier"),
    "admin": ("admin", "agent"),
}


def session_role(user: models.User, app: str) -> str | None:
    """The role `user` signs in to `app` with, or None when they hold none."""
    if app == "customer":
        return "customer"
    held = user.role_set()
    return next((role for role in _APP_ROLES[app] if role in held), None)


# A session for these apps needs the role already: granted by an admin.
_GRANTED_ONLY = {
    "merchant": "Ce numero n'est enregistre dans aucun commerce. Contactez Djassa, ou le gerant si vous y travaillez.",
    "admin": "Ce numero n'a pas acces a l'administration Djassa.",
}


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    app: AppName = "customer"


class OtpRequestOut(BaseModel):
    phone_masked: str
    expires_in: int
    resend_in: int
    # Only with OTP_SENDER=console and OTP_DEV_ECHO=1, never in production.
    dev_code: str | None = None


class OtpVerifyIn(OtpRequestIn):
    code: str = Field(pattern=r"^\d{6}$")


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    phone_masked: str


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=128)


class MeOut(BaseModel):
    sub: str
    role: str
    phone_masked: str | None


def phone_or_422(raw: str, country_code: str) -> str:
    try:
        return normalize_phone(raw, country_code)
    except InvalidPhone as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# One message for every failed verification: wrong, expired, used or
# exhausted codes all look the same from outside.
BAD_CODE = "Code incorrect ou expire. Demandez un nouveau code."


_MESSAGES = {
    "sign_in": "Djassa : votre code est {code}. Il expire dans 5 minutes. Ne le donnez a personne.",
    "change_number": "Djassa : code {code} pour changer le numero de votre compte. Si ce n'est pas vous, ignorez ce message.",
    "recovery": "Djassa : code {code} pour recuperer votre compte sur ce numero. Ne le donnez a personne.",
    "partner": "Djassa Pro : votre code est {code}. Il confirme votre demande d'inscription.",
}


async def send_code(db: AsyncSession, e164: str, purpose: str, now: datetime) -> str:
    """Stores and sends a code for `purpose`, or raises 429/503. Commits.

    The per-number cooldown and hourly cap count codes of every purpose: they
    exist to bound SMS spend, whatever the code is for.
    """
    fixed = test_numbers().get(e164) if purpose == "sign_in" else None
    if fixed is not None:
        AUTH_EVENTS.labels(event="otp_request", result="test_number").inc()
        return fixed
    recent = (
        await db.execute(
            select(models.OtpChallenge)
            .where(models.OtpChallenge.phone_e164 == e164, models.OtpChallenge.created_at > now - timedelta(hours=1))
            .order_by(models.OtpChallenge.created_at.desc())
        )
    ).scalars().all()
    if recent and now - recent[0].created_at < otp.RESEND_AFTER:
        wait = int((otp.RESEND_AFTER - (now - recent[0].created_at)).total_seconds()) + 1
        AUTH_EVENTS.labels(event="otp_request", result="too_soon").inc()
        raise HTTPException(status_code=429, detail=f"Patientez {wait} s avant de redemander un code", headers={"Retry-After": str(wait)})
    if len(recent) >= otp.MAX_SENDS_PER_HOUR:
        AUTH_EVENTS.labels(event="otp_request", result="hourly_cap").inc()
        raise HTTPException(status_code=429, detail="Trop de codes demandes pour ce numero. Reessayez dans une heure.")

    # A new code voids the previous ones for the same purpose, so only the
    # latest SMS works.
    await db.execute(
        update(models.OtpChallenge)
        .where(
            models.OtpChallenge.phone_e164 == e164,
            models.OtpChallenge.purpose == purpose,
            models.OtpChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    code = otp.new_code()
    db.add(
        models.OtpChallenge(
            phone_e164=e164, purpose=purpose, code_hash=otp.hash_code(e164, code), attempts=0,
            expires_at=now + otp.CODE_TTL, created_at=now,
        )
    )
    await db.commit()

    try:
        await get_sender().send(e164, _MESSAGES[purpose].format(code=code))
    except OtpDeliveryFailed:
        AUTH_EVENTS.labels(event="otp_request", result="delivery_failed").inc()
        raise HTTPException(status_code=503, detail="Le SMS n'a pas pu etre envoye. Reessayez dans un instant.")
    AUTH_EVENTS.labels(event="otp_request", result="sent").inc()
    return code


async def check_code(db: AsyncSession, e164: str, code: str, purpose: str, now: datetime) -> None:
    """Consumes the latest `purpose` code for the number, or raises 401.

    On success the caller commits; a wrong guess is committed here so the
    attempt counts even though the request fails.
    """
    fixed = test_numbers().get(e164) if purpose == "sign_in" else None
    if fixed is not None:
        if not hmac.compare_digest(code, fixed):
            AUTH_EVENTS.labels(event="otp_verify", result="wrong_code").inc()
            raise HTTPException(status_code=401, detail=BAD_CODE)
        return
    challenge = (
        await db.execute(
            select(models.OtpChallenge)
            .where(
                models.OtpChallenge.phone_e164 == e164,
                models.OtpChallenge.purpose == purpose,
                models.OtpChallenge.consumed_at.is_(None),
            )
            .order_by(models.OtpChallenge.created_at.desc())
        )
    ).scalars().first()
    if challenge is None or challenge.expires_at <= now or challenge.attempts >= otp.MAX_ATTEMPTS:
        AUTH_EVENTS.labels(event="otp_verify", result="no_code").inc()
        raise HTTPException(status_code=401, detail=BAD_CODE)

    challenge.attempts += 1
    if not otp.code_matches(e164, code, challenge.code_hash):
        await db.commit()
        AUTH_EVENTS.labels(event="otp_verify", result="wrong_code").inc()
        raise HTTPException(status_code=401, detail=BAD_CODE)
    challenge.consumed_at = now


def dev_code(code: str) -> str | None:
    return code if dev_echo_enabled() else None


@router.post("/auth/otp/request", response_model=OtpRequestOut, status_code=202)
@limiter.limit("10/minute;30/hour")
async def request_code(request: Request, payload: OtpRequestIn, db: AsyncSession = Depends(get_db)):
    e164 = phone_or_422(payload.phone, payload.country_code)
    code = await send_code(db, e164, "sign_in", utcnow())
    return OtpRequestOut(
        phone_masked=mask_phone(e164),
        expires_in=int(otp.CODE_TTL.total_seconds()),
        resend_in=int(otp.RESEND_AFTER.total_seconds()),
        dev_code=dev_code(code),
    )


async def issue_tokens(db: AsyncSession, user: models.User, role: str, family: str, now: datetime) -> TokenPairOut:
    refresh = otp.new_refresh_token()
    db.add(
        models.RefreshToken(
            user_id=user.id, token_hash=otp.hash_refresh_token(refresh), family=family, role=role,
            expires_at=now + otp.REFRESH_TTL, created_at=now,
        )
    )
    access = security.create_access_token({"sub": phone_key(user.phone_e164), "role": role}, expires_delta=ACCESS_TTL)
    return TokenPairOut(
        access_token=access, refresh_token=refresh, expires_in=int(ACCESS_TTL.total_seconds()),
        role=role, phone_masked=mask_phone(user.phone_e164),
    )


@router.post("/auth/otp/verify", response_model=TokenPairOut)
@limiter.limit("20/minute")
async def verify_code(request: Request, payload: OtpVerifyIn, db: AsyncSession = Depends(get_db)):
    e164 = phone_or_422(payload.phone, payload.country_code)
    now = utcnow()
    await check_code(db, e164, payload.code, "sign_in", now)

    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if user is None:
        if payload.app in _GRANTED_ONLY:
            await db.commit()
            AUTH_EVENTS.labels(event="otp_verify", result=f"not_{payload.app}").inc()
            raise HTTPException(status_code=403, detail=_GRANTED_ONLY[payload.app])
        user = models.User(phone_e164=e164, roles="customer", disabled=False, created_at=now)
        db.add(user)
        await db.flush()
    if user.disabled:
        await db.commit()
        AUTH_EVENTS.labels(event="otp_verify", result="disabled").inc()
        raise HTTPException(status_code=403, detail="Ce compte est suspendu. Contactez Djassa.")
    role = session_role(user, payload.app)
    if role is None:
        await db.commit()
        AUTH_EVENTS.labels(event="otp_verify", result=f"not_{payload.app}").inc()
        raise HTTPException(status_code=403, detail=_GRANTED_ONLY[payload.app])
    if role == "customer" and "customer" not in user.role_set():
        # Proving a number is all a customer account needs.
        user.roles = ",".join(sorted(user.role_set() | {"customer"}))

    user.last_login_at = now
    pair = await issue_tokens(db, user, role, otp.new_family(), now)
    await db.commit()
    AUTH_EVENTS.labels(event="otp_verify", result="ok").inc()
    return pair


@router.post("/auth/refresh", response_model=TokenPairOut)
@limiter.limit("30/minute")
async def refresh(request: Request, payload: RefreshIn, db: AsyncSession = Depends(get_db)):
    now = utcnow()
    stored = (
        await db.execute(
            select(models.RefreshToken).where(models.RefreshToken.token_hash == otp.hash_refresh_token(payload.refresh_token))
        )
    ).scalar_one_or_none()
    if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
        AUTH_EVENTS.labels(event="refresh", result="invalid").inc()
        raise HTTPException(status_code=401, detail="Session expiree. Reconnectez-vous.")
    if stored.rotated_at is not None:
        # Already exchanged once: whoever holds it now copied it. End that
        # whole session on every copy; the real owner signs in again.
        await db.execute(
            update(models.RefreshToken)
            .where(models.RefreshToken.family == stored.family, models.RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        AUTH_EVENTS.labels(event="refresh", result="reuse_detected").inc()
        raise HTTPException(status_code=401, detail="Session expiree. Reconnectez-vous.")

    user = await db.get(models.User, stored.user_id)
    if user is None or user.disabled or stored.role not in user.role_set():
        stored.revoked_at = now
        await db.commit()
        AUTH_EVENTS.labels(event="refresh", result="denied").inc()
        raise HTTPException(status_code=401, detail="Session expiree. Reconnectez-vous.")

    stored.rotated_at = now
    pair = await issue_tokens(db, user, stored.role, stored.family, now)
    await db.commit()
    AUTH_EVENTS.labels(event="refresh", result="ok").inc()
    return pair


@router.post("/auth/logout", status_code=204)
async def logout(payload: RefreshIn, db: AsyncSession = Depends(get_db)):
    """Revokes the session on this device. Idempotent; never reveals whether
    the token existed. The current access token lives out its hour."""
    stored = (
        await db.execute(
            select(models.RefreshToken).where(models.RefreshToken.token_hash == otp.hash_refresh_token(payload.refresh_token))
        )
    ).scalar_one_or_none()
    if stored is not None:
        await db.execute(
            update(models.RefreshToken)
            .where(models.RefreshToken.family == stored.family, models.RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await db.commit()


@router.get("/auth/me", response_model=MeOut)
async def me(user=Depends(security.get_current_user)):
    sub = user["username"]
    masked = mask_phone(sub[4:]) if sub.startswith("tel:") else None
    return MeOut(sub=sub, role=user["role"], phone_masked=masked)


# --- Admin: who may run a shop, enroll shops, administer --------------------


class GrantRoleIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    role: Literal["merchant", "agent", "admin"]
    # With role=merchant: the venue this number will run from the merchant app.
    venue_id: int | None = None


class GrantRoleOut(BaseModel):
    phone_masked: str
    roles: list[str]
    venue_id: int | None


@router.post("/admin/users/roles", response_model=GrantRoleOut)
async def grant_role(payload: GrantRoleIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))):
    e164 = phone_or_422(payload.phone, payload.country_code)
    now = utcnow()
    venue = None
    if payload.venue_id is not None:
        if payload.role != "merchant":
            raise HTTPException(status_code=422, detail="venue_id only applies to role=merchant")
        venue = await db.get(models.Venue, payload.venue_id)
        if venue is None:
            raise HTTPException(status_code=404, detail="Venue not found")

    if venue is not None:
        user = await link_merchant(db, e164, venue, now)
    else:
        user = await ensure_role(db, e164, payload.role, now)
    await db.commit()
    return GrantRoleOut(phone_masked=mask_phone(e164), roles=sorted(user.role_set()), venue_id=payload.venue_id)


async def ensure_role(db: AsyncSession, e164: str, role: str, now: datetime) -> models.User:
    """The account for `e164`, created if needed, holding `role`."""
    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if user is None:
        user = models.User(phone_e164=e164, roles=role, disabled=False, created_at=now)
        db.add(user)
    else:
        user.roles = ",".join(sorted(user.role_set() | {role}))
    return user


async def link_merchant(db: AsyncSession, e164: str, venue: models.Venue, now: datetime) -> models.User:
    """Makes `e164` the merchant who runs `venue` from Djassa Pro.

    One number runs one shop: the merchant app finds "my shop" from the
    token alone, so a second one would be picked at random.
    """
    key = phone_key(e164)
    other = (
        await db.execute(select(models.Venue.name).where(models.Venue.owner_username == key, models.Venue.id != venue.id))
    ).scalars().first()
    if other is not None:
        raise HTTPException(status_code=409, detail=f"Ce numero gere deja un commerce : {other}")
    # Djassa Pro opens the owner's session first, so a cashier made owner
    # would silently lose their cashier shop. The owner there removes them first.
    employer = (
        await db.execute(
            select(models.Venue.name)
            .join(models.VenueStaff, models.VenueStaff.venue_id == models.Venue.id)
            .where(models.VenueStaff.user_key == key, models.VenueStaff.removed_at.is_(None))
        )
    ).scalars().first()
    if employer is not None:
        raise HTTPException(status_code=409, detail=f"Ce numero est caissier chez {employer}. Le gerant doit d'abord le retirer de son equipe.")
    user = await ensure_role(db, e164, "merchant", now)
    venue.owner_username = key
    return user
