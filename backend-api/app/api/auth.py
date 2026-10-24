"""Sessions: tokens, refresh, logout and the roles an admin grants.

Sign-in itself (phone + password) lives in `app/api/password_auth.py`. The
token subject is `phone_key(e164)`, the key counter loyalty already uses, so a
customer's counter points follow them into the app once they prove the number.

    POST /api/auth/refresh       {refresh_token}      -> rotated pair
    POST /api/auth/logout        {refresh_token}      -> session revoked
    GET  /api/auth/me
    POST /api/admin/users/roles  (admin) grant merchant/admin, link a venue

The old SMS-code routes answer 410 so a build that still has them shows an
"update the app" message instead of a broken screen.

`app` is "customer", "merchant" or "admin". Anyone can open a customer
session; the other two need a role, which only an admin grants.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core import security, tokens
from ..core.phone import InvalidPhone, mask_phone, normalize_phone, phone_key
from ..db import get_db
from ..metrics import AUTH_EVENTS
from ..rate_limiter import limiter
from ..services import account_checks

router = APIRouter()
log = logging.getLogger("fidelia.auth")

ACCESS_TTL = timedelta(minutes=60)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Apps and the sessions they open ---------------------------------------

AppName = Literal["customer", "merchant", "admin"]

# The session each app opens, best first: Fidelia Pro opens an owner's session
# for an owner and a cashier's for a cashier, fidelia-installer an admin's or a
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
    "merchant": "Ce numero n'est enregistre dans aucun commerce. Contactez Fidelia, ou le gerant si vous y travaillez.",
    "admin": "Ce numero n'a pas acces a l'administration Fidelia.",
}


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    phone_masked: str
    # Password sign-in: whether the number is proven, and whether a temporary
    # password must be replaced first. Mirrored in the `vf` and `pc` claims.
    verified: bool = False
    must_change_password: bool = False


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=128)


class MeOut(BaseModel):
    sub: str
    role: str
    phone_masked: str | None
    verified: bool = True
    must_change_password: bool = False
    # The team looked at this number and turned it down.
    number_refused: bool = False


def phone_or_422(raw: str, country_code: str) -> str:
    try:
        return normalize_phone(raw, country_code)
    except InvalidPhone as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Builds that still carry the SMS-code screens get a message to show.
UPDATE_APP = "Mettez a jour l'application Fidelia pour vous connecter."


@router.post("/auth/otp/request", include_in_schema=False)
@router.post("/auth/otp/verify", include_in_schema=False)
async def sms_codes_are_gone():
    raise HTTPException(status_code=410, detail=UPDATE_APP)


async def issue_tokens(db: AsyncSession, user: models.User, role: str, family: str, now: datetime) -> TokenPairOut:
    refresh = tokens.new_refresh_token()
    db.add(
        models.RefreshToken(
            user_id=user.id, token_hash=tokens.hash_refresh_token(refresh), family=family, role=role,
            expires_at=now + tokens.REFRESH_TTL, created_at=now,
        )
    )
    verified = bool(user.phone_verified_at)
    must_change = bool(user.must_change_password)
    access = security.create_access_token(
        {"sub": phone_key(user.phone_e164), "role": role, "vf": verified, "pc": must_change}, expires_delta=ACCESS_TTL
    )
    return TokenPairOut(
        access_token=access, refresh_token=refresh, expires_in=int(ACCESS_TTL.total_seconds()),
        role=role, phone_masked=mask_phone(user.phone_e164), verified=verified, must_change_password=must_change,
    )


@router.post("/auth/refresh", response_model=TokenPairOut)
@limiter.limit("30/minute")
async def refresh(request: Request, payload: RefreshIn, db: AsyncSession = Depends(get_db)):
    now = utcnow()
    stored = (
        await db.execute(
            select(models.RefreshToken).where(models.RefreshToken.token_hash == tokens.hash_refresh_token(payload.refresh_token))
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
            select(models.RefreshToken).where(models.RefreshToken.token_hash == tokens.hash_refresh_token(payload.refresh_token))
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
async def me(user=Depends(security.get_session_user), db: AsyncSession = Depends(get_db)):
    sub = user["username"]
    masked = mask_phone(sub[4:]) if sub.startswith("tel:") else None
    refused = False
    if sub.startswith("tel:") and not user["verified"]:
        latest = (
            await db.execute(
                select(models.AccountCheck.status)
                .join(models.User, models.User.id == models.AccountCheck.user_id)
                .where(models.User.phone_e164 == sub[4:], models.AccountCheck.kind == "verify_number")
                .order_by(models.AccountCheck.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        refused = latest == "refused"
    return MeOut(
        sub=sub, role=user["role"], phone_masked=masked,
        verified=user["verified"], must_change_password=user["must_change_password"],
        number_refused=refused,
    )


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
    """The account for `e164`, created if needed, holding `role`.

    A login the team creates, or one that never had a password, waits in the
    team's queue for a temporary password sent on WhatsApp (the hash stays
    empty; that password signs in, and must be replaced). Someone who already
    has a password keeps it and gets no check.
    """
    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if user is None:
        user = models.User(phone_e164=e164, roles=role, disabled=False, created_at=now)
        db.add(user)
        await db.flush()
    else:
        user.roles = ",".join(sorted(user.role_set() | {role}))
    if not user.password_hash:
        user.must_change_password = True
        check = await account_checks.open_check(db, user, "reset_password", now, team_created=True)
        check.team_created = True
    return user


async def link_merchant(db: AsyncSession, e164: str, venue: models.Venue, now: datetime) -> models.User:
    """Makes `e164` the merchant who runs `venue` from Fidelia Pro.

    One number runs one shop: the merchant app finds "my shop" from the
    token alone, so a second one would be picked at random.
    """
    key = phone_key(e164)
    other = (
        await db.execute(select(models.Venue.name).where(models.Venue.owner_username == key, models.Venue.id != venue.id))
    ).scalars().first()
    if other is not None:
        raise HTTPException(status_code=409, detail=f"Ce numero gere deja un commerce : {other}")
    # Fidelia Pro opens the owner's session first, so a cashier made owner
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
