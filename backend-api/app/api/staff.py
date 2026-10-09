"""A shop's cashiers, managed by its owner from Fidelia Pro.

    GET    /api/merchant/staff          the active cashiers
    POST   /api/merchant/staff          {phone, name?}  add one
    DELETE /api/merchant/staff/{id}     remove one

A cashier signs in to Fidelia Pro with their own number and gets a "cashier"
session (`auth.session_role`): sales, payment requests, the pay QR and counter
points, never Wave, payouts, deals, photos, location, statements or staff
(`security.SHOP_STAFF`). A number works at one shop at a time and cannot work
at a shop as well as own one. Removal is immediate: `_my_venue` looks the link
up on every request, and the cashier's sessions are revoked.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.phone import mask_phone, phone_key
from ..core.security import require_role
from ..db import get_db
from ..services.account_move import revoke_role_sessions
from .auth import ensure_role, phone_or_422, utcnow
from .onboarding import _notify
from .payment_requests import _my_venue

router = APIRouter()

MAX_CASHIERS = 10


class StaffIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    name: str | None = Field(default=None, max_length=80)


class StaffOut(BaseModel):
    id: int
    phone_masked: str
    name: str | None
    role: str
    created_at: datetime
    # Whether they have signed in since being added: "invited" until then.
    last_login_at: datetime | None


async def _out(db: AsyncSession, row: models.VenueStaff) -> StaffOut:
    e164 = row.user_key[4:] if row.user_key.startswith("tel:") else row.user_key
    last_login = (
        await db.execute(select(models.User.last_login_at).where(models.User.phone_e164 == e164))
    ).scalar_one_or_none()
    return StaffOut(
        id=row.id, phone_masked=mask_phone(e164), name=row.name, role=row.role,
        created_at=row.created_at, last_login_at=last_login if last_login and last_login >= row.created_at else None,
    )


@router.get("/merchant/staff", response_model=list[StaffOut])
async def list_staff(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    rows = (
        await db.execute(
            select(models.VenueStaff)
            .where(models.VenueStaff.venue_id == venue.id, models.VenueStaff.removed_at.is_(None))
            .order_by(models.VenueStaff.created_at)
        )
    ).scalars().all()
    return [await _out(db, r) for r in rows]


@router.post("/merchant/staff", response_model=StaffOut, status_code=201)
async def add_staff(payload: StaffIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    e164 = phone_or_422(payload.phone, payload.country_code)
    key = phone_key(e164)
    if key == user["username"]:
        raise HTTPException(status_code=422, detail="C'est votre propre numero : vous avez deja acces a tout.")
    owned = (await db.execute(select(models.Venue.name).where(models.Venue.owner_username == key))).scalars().first()
    if owned is not None:
        raise HTTPException(status_code=409, detail=f"Ce numero gere deja un commerce : {owned}")
    current = (
        await db.execute(
            select(models.VenueStaff).where(models.VenueStaff.user_key == key, models.VenueStaff.removed_at.is_(None))
        )
    ).scalars().first()
    if current is not None:
        if current.venue_id == venue.id:
            raise HTTPException(status_code=409, detail="Ce numero fait deja partie de votre equipe")
        raise HTTPException(status_code=409, detail="Ce numero travaille deja dans un autre commerce Fidelia")
    active = (
        await db.execute(
            select(func.count(models.VenueStaff.id)).where(
                models.VenueStaff.venue_id == venue.id, models.VenueStaff.removed_at.is_(None)
            )
        )
    ).scalar_one()
    if active >= MAX_CASHIERS:
        raise HTTPException(status_code=409, detail=f"{MAX_CASHIERS} caissiers au plus par commerce. Retirez-en un d'abord.")

    now = utcnow()
    await ensure_role(db, e164, "cashier", now)
    row = models.VenueStaff(
        venue_id=venue.id, user_key=key, name=(payload.name or "").strip() or None, role="cashier",
        added_by=user["username"], created_at=now,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await _notify(e164, f"Fidelia Pro : {venue.name} vous a ajoute a son equipe. Installez Fidelia Pro et connectez-vous avec ce numero.")
    return await _out(db, row)


@router.delete("/merchant/staff/{staff_id}", status_code=204)
async def remove_staff(staff_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    row = await db.get(models.VenueStaff, staff_id)
    # Another shop's cashier answers exactly like a missing one.
    if row is None or row.venue_id != venue.id or row.removed_at is not None:
        raise HTTPException(status_code=404, detail="Membre de l'equipe introuvable")
    now = utcnow()
    row.removed_at, row.removed_by = now, user["username"]
    e164 = row.user_key[4:] if row.user_key.startswith("tel:") else row.user_key
    account = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if account is not None:
        account.roles = ",".join(sorted(account.role_set() - {"cashier"})) or "customer"
        await revoke_role_sessions(db, account.id, "cashier", now)
    await db.commit()
