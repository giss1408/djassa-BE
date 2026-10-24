"""Sign-in with a phone number and a password.

    POST /api/auth/register  {phone, password, app: "customer"} -> 201 session, not yet verified
                             (an existing account: 202, no session; see /auth/claim)
    POST /api/auth/claim     {phone, code, password, app}       -> session
    POST /api/auth/login     {phone, password, app}             -> session

A new number is proven afterwards by a one-time check the team sends on
WhatsApp (app/services/account_checks.py); until then the session carries
`vf: false`.
"""

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core import passwords, security, tokens
from ..core.phone import phone_key
from ..db import get_db
from ..metrics import AUTH_EVENTS
from ..rate_limiter import limiter
from ..services import account_checks, account_move, loyalty_consent
from .auth import _GRANTED_ONLY, AppName, TokenPairOut, issue_tokens, phone_or_422, session_role, utcnow

router = APIRouter()

MAX_FAILED_LOGINS = 5
LOCK_FOR = timedelta(minutes=15)
BAD_LOGIN = "Numero ou mot de passe incorrect."
LOCKED = "Trop d'essais. Reessayez dans 15 minutes."
SUSPENDED = "Ce compte est suspendu. Contactez Fidelia."
BAD_CODE = "Code incorrect ou expire."
CLAIM_ANSWER = "Fidelia va vous envoyer un code sur WhatsApp. Saisissez-le avec votre mot de passe."

# Checked when the number is unknown, so a miss costs the same time as a hit.
_DUMMY_HASH = passwords.hash_password("fidelia-dummy-password")


class RegisterIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    password: str = Field(min_length=1, max_length=256)
    app: Literal["customer"] = "customer"
    # The loyalty wording version agreed to on the sign-up screen; kept on the
    # verification check and granted once the team confirms the number.
    loyalty_consent_version: str | None = Field(default=None, min_length=1, max_length=64)


class LoginIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    password: str = Field(min_length=1, max_length=256)
    app: AppName = "customer"


@router.post("/auth/register", response_model=TokenPairOut, status_code=201, responses={202: {}})
@limiter.limit("5/minute;20/hour")
async def register(request: Request, payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    e164 = phone_or_422(payload.phone, payload.country_code)
    try:
        passwords.check_rules(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = utcnow()
    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if user is not None and user.password_hash:
        AUTH_EVENTS.labels(event="register", result="exists").inc()
        raise HTTPException(status_code=409, detail="Ce numero a deja un compte. Connectez-vous.")
    if user is not None:
        # The account exists but has no password yet (created by SMS sign-in or
        # by the team). Whoever typed the number may not hold it: nothing on the
        # account changes and no session is issued. The team sends a code to
        # the number, and /auth/claim sets the password with it. A suspended
        # account gets the same answer, so it does not reveal the suspension.
        if not user.disabled:
            check = await account_checks.open_check(db, user, "verify_number", now)
            if payload.loyalty_consent_version:
                check.consent_version = payload.loyalty_consent_version
            await db.commit()
        AUTH_EVENTS.labels(event="register", result="claim").inc()
        return JSONResponse(status_code=202, content={"message": CLAIM_ANSWER})
    user = models.User(phone_e164=e164, roles="customer", disabled=False, created_at=now)
    db.add(user)
    await db.flush()
    user.password_hash = passwords.hash_password(payload.password)
    check = await account_checks.open_check(db, user, "verify_number", now)
    check.consent_version = payload.loyalty_consent_version
    user.last_login_at = now
    pair = await issue_tokens(db, user, "customer", tokens.new_family(), now)
    await db.commit()
    AUTH_EVENTS.labels(event="register", result="ok").inc()
    return pair


@router.post("/auth/login", response_model=TokenPairOut)
@limiter.limit("10/minute;30/hour")
async def login(request: Request, payload: LoginIn, db: AsyncSession = Depends(get_db)):
    e164 = phone_or_422(payload.phone, payload.country_code)
    now = utcnow()
    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if user is None:
        passwords.verify_password(payload.password, _DUMMY_HASH)
        AUTH_EVENTS.labels(event="login", result="unknown").inc()
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    if user.locked_until is not None and user.locked_until > now:
        AUTH_EVENTS.labels(event="login", result="locked").inc()
        raise HTTPException(status_code=423, detail=LOCKED)
    matched = bool(user.password_hash) and passwords.verify_password(payload.password, user.password_hash)
    temporary = False
    if not matched:
        # A temporary password sent by the team also works, even for a login
        # the team created without any password.
        temporary = await account_checks.use_temporary_password(db, user, payload.password, now)
    if not matched and not temporary and not user.password_hash and not await _temporary_sent(db, user):
        raise HTTPException(status_code=409, detail="password_not_set")
    if not matched and not temporary:
        # Incremented in SQL so concurrent wrong guesses cannot undercount.
        misses = (
            await db.execute(
                update(models.User)
                .where(models.User.id == user.id)
                .values(failed_logins=models.User.failed_logins + 1)
                .returning(models.User.failed_logins)
            )
        ).scalar_one()
        locked = misses >= MAX_FAILED_LOGINS
        if locked:
            await db.execute(
                update(models.User)
                .where(models.User.id == user.id)
                .values(failed_logins=0, locked_until=now + LOCK_FOR)
            )
        await db.commit()
        AUTH_EVENTS.labels(event="login", result="locked" if locked else "wrong_password").inc()
        raise HTTPException(status_code=401, detail=BAD_LOGIN)

    # Only a correct password learns anything about the account.
    if user.disabled:
        AUTH_EVENTS.labels(event="login", result="disabled").inc()
        raise HTTPException(status_code=403, detail=SUSPENDED)
    role = session_role(user, payload.app)
    if role is None:
        AUTH_EVENTS.labels(event="login", result=f"not_{payload.app}").inc()
        raise HTTPException(status_code=403, detail=_GRANTED_ONLY[payload.app])
    if temporary:
        # The team sent it to this number, so the number is proven; the
        # password must be replaced before anything else.
        user.must_change_password = True
        if user.phone_verified_at is None:
            user.phone_verified_at = now
        # Whoever held a session before the reset is signed out.
        await account_move.revoke_all_sessions(db, user.id, now)
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    pair = await issue_tokens(db, user, role, tokens.new_family(), now)
    await db.commit()
    AUTH_EVENTS.labels(event="login", result="temporary" if temporary else "ok").inc()
    return pair


async def _temporary_sent(db: AsyncSession, user: models.User) -> bool:
    """True when the team has sent this user a temporary password."""
    found = (
        await db.execute(
            select(models.AccountCheck.id).where(
                models.AccountCheck.user_id == user.id,
                models.AccountCheck.kind == "reset_password",
                models.AccountCheck.status == "sent",
            )
        )
    ).first()
    return found is not None


class ClaimIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    code: str = Field(min_length=1, max_length=16)
    password: str = Field(min_length=1, max_length=256)
    app: AppName = "customer"
    loyalty_consent_version: str | None = Field(default=None, min_length=1, max_length=64)


@router.post("/auth/claim", response_model=TokenPairOut)
@limiter.limit("10/minute;30/hour")
async def claim(request: Request, payload: ClaimIn, db: AsyncSession = Depends(get_db)):
    """Sets the first password of an existing account with the code the team
    sent to its number on WhatsApp (after register answered 202)."""
    e164 = phone_or_422(payload.phone, payload.country_code)
    try:
        passwords.check_rules(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = utcnow()
    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail=BAD_CODE)
    try:
        check = await account_checks.verify_code(db, user, "verify_number", payload.code.replace(" ", ""), now)
    except account_checks.BadCode:
        AUTH_EVENTS.labels(event="claim", result="bad_code").inc()
        raise HTTPException(status_code=401, detail=BAD_CODE)
    if user.disabled:
        await db.commit()
        raise HTTPException(status_code=403, detail=SUSPENDED)
    user.password_hash = passwords.hash_password(payload.password)
    user.phone_verified_at = now
    user.must_change_password = False
    user.failed_logins = 0
    user.locked_until = None
    consent_version = payload.loyalty_consent_version or check.consent_version
    if consent_version and payload.app == "customer":
        await loyalty_consent.grant(
            db, phone_key(user.phone_e164), source=loyalty_consent.APP, version=consent_version, now=now
        )
    # Sessions opened before the number was proven are not trusted.
    await account_move.revoke_all_sessions(db, user.id, now)
    role = session_role(user, payload.app)
    if role is None:
        await db.commit()
        AUTH_EVENTS.labels(event="claim", result=f"not_{payload.app}").inc()
        raise HTTPException(status_code=403, detail=_GRANTED_ONLY[payload.app])
    user.last_login_at = now
    pair = await issue_tokens(db, user, role, tokens.new_family(), now)
    await db.commit()
    AUTH_EVENTS.labels(event="claim", result="ok").inc()
    return pair


class VerifyNumberIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


class ChangeNumberIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


async def _session_account(db: AsyncSession, session: dict) -> models.User:
    """The User behind a phone session; demo accounts have none."""
    sub = session["username"]
    user = None
    if sub.startswith("tel:"):
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == sub[4:]))).scalar_one_or_none()
    if user is None or user.disabled:
        raise HTTPException(status_code=403, detail="Disponible uniquement pour un compte connecte par telephone")
    return user


@router.post("/auth/verify-number", response_model=TokenPairOut)
@limiter.limit("10/minute")
async def verify_number(
    request: Request,
    payload: VerifyNumberIn,
    db: AsyncSession = Depends(get_db),
    session=Depends(security.get_session_user),
):
    user = await _session_account(db, session)
    now = utcnow()
    try:
        check = await account_checks.verify_code(db, user, "verify_number", payload.code.replace(" ", ""), now)
    except account_checks.BadCode:
        AUTH_EVENTS.labels(event="verify_number", result="bad_code").inc()
        raise HTTPException(status_code=401, detail=BAD_CODE)
    user.phone_verified_at = now
    role = session["role"]
    if check.consent_version and role == "customer":
        await loyalty_consent.grant(
            db, phone_key(user.phone_e164), source=loyalty_consent.APP, version=check.consent_version, now=now
        )
    # Only the session that proved the number survives.
    await account_move.revoke_all_sessions(db, user.id, now)
    pair = await issue_tokens(db, user, role, tokens.new_family(), now)
    await db.commit()
    AUTH_EVENTS.labels(event="verify_number", result="ok").inc()
    return pair


@router.post("/auth/number", response_model=TokenPairOut)
@limiter.limit("5/minute;20/hour")
async def correct_number(
    request: Request,
    payload: ChangeNumberIn,
    db: AsyncSession = Depends(get_db),
    session=Depends(security.get_session_user),
):
    """Fixes a mistyped number before it was ever verified."""
    if session["verified"]:
        raise HTTPException(status_code=403, detail="Ce numero est deja verifie.")
    user = await _session_account(db, session)
    if user.phone_verified_at is not None:
        raise HTTPException(status_code=403, detail="Ce numero est deja verifie.")
    # Only an account this sign-up created, still empty, may move; anything
    # else goes through the team (recovery).
    if user.role_set() != {"customer"} or not await account_move.owns_nothing(db, phone_key(user.phone_e164)):
        raise HTTPException(status_code=403, detail="Contactez Fidelia pour changer de numero.")
    e164 = phone_or_422(payload.phone, payload.country_code)
    now = utcnow()
    if e164 == user.phone_e164:
        raise HTTPException(status_code=422, detail="C'est deja le numero de ce compte")
    taken = (await db.execute(select(models.User.id).where(models.User.phone_e164 == e164))).first()
    if taken is not None:
        raise HTTPException(status_code=409, detail="Ce numero est deja utilise.")
    # A code sent to the old number must stop working.
    old = (
        await db.execute(
            select(models.AccountCheck).where(
                models.AccountCheck.user_id == user.id,
                models.AccountCheck.kind == "verify_number",
                models.AccountCheck.status.in_(account_checks.OPEN_STATUSES),
            )
        )
    ).scalars().all()
    consent_version = None
    for check in old:
        consent_version = consent_version or check.consent_version
        await account_checks.refuse(db, check, now)
    user.phone_e164 = e164
    await account_move.revoke_all_sessions(db, user.id, now)
    fresh = await account_checks.open_check(db, user, "verify_number", now)
    fresh.consent_version = consent_version
    pair = await issue_tokens(db, user, session["role"], tokens.new_family(), now)
    await db.commit()
    return pair


RESET_ANSWER = "Si ce numero a un compte, Fidelia vous enverra un mot de passe temporaire sur WhatsApp."


class PasswordResetIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


class ChangePasswordIn(BaseModel):
    current: str | None = Field(default=None, max_length=256)
    new: str = Field(min_length=1, max_length=256)


@router.post("/auth/password-reset", status_code=202)
@limiter.limit("5/minute;20/hour")
async def password_reset(request: Request, payload: PasswordResetIn, db: AsyncSession = Depends(get_db)):
    """Asks the team for a temporary password. The answer never tells whether
    the number has an account."""
    e164 = phone_or_422(payload.phone, payload.country_code)
    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if user is not None and not user.disabled:
        await account_checks.open_check(db, user, "reset_password", utcnow())
        await db.commit()
    AUTH_EVENTS.labels(event="password_reset", result="asked").inc()
    return {"message": RESET_ANSWER}


@router.post("/auth/password", response_model=TokenPairOut)
@limiter.limit("5/minute;20/hour")
async def change_password(
    request: Request,
    payload: ChangePasswordIn,
    db: AsyncSession = Depends(get_db),
    session=Depends(security.get_session_user),
):
    user = await _session_account(db, session)
    # Only a session opened with a temporary password (pc claim) may skip the
    # old one; the account flag alone is not enough.
    if not (session["must_change_password"] and user.must_change_password):
        if not user.password_hash or not payload.current or not passwords.verify_password(payload.current, user.password_hash):
            raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect.")
    try:
        passwords.check_rules(payload.new)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = utcnow()
    user.password_hash = passwords.hash_password(payload.new)
    user.must_change_password = False
    # A temporary password sent but not yet used must stop working.
    pending = (
        await db.execute(
            select(models.AccountCheck).where(
                models.AccountCheck.user_id == user.id,
                models.AccountCheck.kind == "reset_password",
                models.AccountCheck.status.in_(account_checks.OPEN_STATUSES),
            )
        )
    ).scalars().all()
    for check in pending:
        await account_checks.refuse(db, check, now)
    await account_move.revoke_all_sessions(db, user.id, now)
    pair = await issue_tokens(db, user, session["role"], tokens.new_family(), now)
    await db.commit()
    AUTH_EVENTS.labels(event="password_change", result="ok").inc()
    return pair
