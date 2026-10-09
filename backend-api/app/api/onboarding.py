"""Bringing a merchant in: their shop, their login, their QR.

Two doors to the same room:

* **A field agent or admin enrols the merchant** in one call:
      POST /api/admin/venues
  creates the shop, makes the merchant's phone its login, and issues the
  Fidelia QR code when a wallet is given. The shop records who enrolled it;
  an agent sees their own shops at
      GET  /api/agent/venues
* **The merchant asks to join** from the Fidelia Pro sign-in screen:
      POST /api/partner-requests/code   code to their phone
      POST /api/partner-requests        what the shop is
  and an admin reviews it, confirming APPROVAL_CHECKS before approving:
      GET  /api/admin/partner-requests
      POST /api/admin/partner-requests/{id}/approve   (same as POST /admin/venues)
      POST /api/admin/partner-requests/{id}/reject
  The merchant is told by SMS either way, and signs in with the same number.

Wave comes after, from Fidelia Pro itself (`app/api/wave.py`): the merchant's
own account, points only by default.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core import otp, security
from ..core.phone import mask_phone
from ..db import get_db
from ..rate_limiter import limiter
from ..services.otp_sender import OtpDeliveryFailed, get_sender
from .auth import check_code, dev_code, link_merchant, phone_or_422, send_code, utcnow
from .customer import CATEGORIES, new_pay_code, qr_payload
from .customer import _venue_out as _public_venue_out
from ..schemas.customer import VenueOut as PublicVenueOut

router = APIRouter()

Category = Literal["maquis", "restaurant", "superette", "pharmacy", "mode", "beaute", "telephonie"]
WalletProvider = Literal["wave", "orange", "mtn", "moov"]

assert set(Category.__args__) == set(CATEGORIES), "keep Category in step with customer.CATEGORIES"


async def _notify(e164: str, message: str) -> None:
    """Best effort: a failed courtesy SMS must not undo the decision."""
    try:
        await get_sender().send(e164, message)
    except (OtpDeliveryFailed, RuntimeError):
        pass


# --- Enrol a shop in one call ------------------------------------------------


class VenueIn(BaseModel):
    category: Category
    name: str = Field(min_length=2, max_length=255)
    commune: str = Field(min_length=2, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32, description="The shop's public phone, shown to customers")
    opening_hours: str | None = Field(default=None, max_length=255)
    specialties: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    points_per_100: int = Field(default=1, ge=0, le=20)
    # The merchant's own wallet that customers pay into. Without it the shop
    # is listed and runs loyalty, but has no Fidelia payment QR.
    payout_provider: WalletProvider | None = None
    payout_account: str | None = Field(default=None, max_length=32)
    # The merchant's login for Fidelia Pro. Usually also the wallet number.
    merchant_phone: str | None = Field(default=None, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


class VenueOut(BaseModel):
    id: int
    name: str
    category: str
    commune: str
    payout_provider: str | None
    merchant_phone_masked: str | None
    pay_code: str | None
    qr_payload: str | None


def _venue_out(venue: models.Venue) -> VenueOut:
    owner = venue.owner_username or ""
    return VenueOut(
        id=venue.id, name=venue.name, category=venue.category, commune=venue.commune,
        payout_provider=venue.payout_provider,
        merchant_phone_masked=mask_phone(owner[4:]) if owner.startswith("tel:") else None,
        pay_code=venue.pay_code, qr_payload=qr_payload(venue.pay_code) if venue.pay_code else None,
    )


async def create_venue(db: AsyncSession, payload: VenueIn, now: datetime, enrolled_by: str | None = None) -> models.Venue:
    """Creates the shop, links its merchant and issues its QR. The caller commits."""
    if bool(payload.payout_provider) != bool(payload.payout_account):
        raise HTTPException(status_code=422, detail="payout_provider and payout_account go together")
    wallet = phone_or_422(payload.payout_account, payload.country_code) if payload.payout_account else None
    venue = models.Venue(
        category=payload.category, name=payload.name.strip(), commune=payload.commune.strip(),
        address=payload.address, phone=payload.phone, opening_hours=payload.opening_hours,
        specialties=payload.specialties, description=payload.description,
        points_per_100=payload.points_per_100, payout_provider=payload.payout_provider,
        payout_account=wallet, is_sample=False,
        # The Fidelia QR only makes sense when there is a wallet to pay into.
        pay_code=new_pay_code() if wallet else None,
        enrolled_by=enrolled_by,
    )
    db.add(venue)
    await db.flush()
    if payload.merchant_phone:
        await link_merchant(db, phone_or_422(payload.merchant_phone, payload.country_code), venue, now)
    return venue


@router.post("/admin/venues", response_model=VenueOut, status_code=201)
async def admin_create_venue(
    payload: VenueIn, db: AsyncSession = Depends(get_db), user=Depends(security.require_role("admin", "agent"))
):
    """Enrols a shop on site. A field agent must give the owner's number: a
    shop enrolled in person without its merchant would wait for an admin."""
    if user["role"] == "agent" and not payload.merchant_phone:
        raise HTTPException(status_code=422, detail="Indiquez le numero du gerant")
    venue = await create_venue(db, payload, utcnow(), enrolled_by=user["username"])
    await db.commit()
    if venue.owner_username and venue.owner_username.startswith("tel:"):
        await _notify(venue.owner_username[4:], f"Fidelia Pro : {venue.name} est inscrit. Connectez-vous a Fidelia Pro avec ce numero.")
    return _venue_out(venue)


@router.get("/agent/venues", response_model=list[VenueOut])
async def agent_my_venues(db: AsyncSession = Depends(get_db), user=Depends(security.require_role("agent", "admin"))):
    """The shops this field agent (or admin) enrolled, newest first."""
    rows = (
        await db.execute(
            select(models.Venue).where(models.Venue.enrolled_by == user["username"]).order_by(models.Venue.id.desc()).limit(300)
        )
    ).scalars().all()
    return [_venue_out(v) for v in rows]


# --- The merchant asks to join -----------------------------------------------


class PartnerCodeIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


class PartnerRequestIn(PartnerCodeIn):
    code: str = Field(pattern=r"^\d{6}$")
    contact_name: str = Field(min_length=2, max_length=120)
    shop_name: str = Field(min_length=2, max_length=255)
    category: Category
    commune: str = Field(min_length=2, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    wallet_provider: WalletProvider | None = None
    # Defaults to the phone above, which is usually the merchant's wallet.
    wallet_number: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=1000)


class PartnerRequestOut(BaseModel):
    id: int
    phone: str
    contact_name: str
    shop_name: str
    category: str
    commune: str
    address: str | None
    wallet_provider: str | None
    wallet_number: str | None
    notes: str | None
    status: str
    venue_id: int | None
    decision_note: str | None
    decided_by: str | None
    review_checks: list[str]
    created_at: datetime
    decided_at: datetime | None


def _request_out(r: models.PartnerRequest) -> PartnerRequestOut:
    return PartnerRequestOut(
        id=r.id, phone=r.phone_e164, contact_name=r.contact_name, shop_name=r.shop_name, category=r.category,
        commune=r.commune, address=r.address, wallet_provider=r.wallet_provider, wallet_number=r.wallet_number,
        notes=r.notes, status=r.status, venue_id=r.venue_id, decision_note=r.decision_note,
        decided_by=r.decided_by, review_checks=(r.review_checks or "").split(",") if r.review_checks else [],
        created_at=r.created_at, decided_at=r.decided_at,
    )


@router.post("/partner-requests/code", status_code=202)
@limiter.limit("5/minute;20/hour")
async def partner_code(request: Request, payload: PartnerCodeIn, db: AsyncSession = Depends(get_db)):
    e164 = phone_or_422(payload.phone, payload.country_code)
    code = await send_code(db, e164, "partner", utcnow())
    return {
        "phone_masked": mask_phone(e164),
        "expires_in": int(otp.CODE_TTL.total_seconds()),
        "resend_in": int(otp.RESEND_AFTER.total_seconds()),
        "dev_code": dev_code(code),
    }


@router.post("/partner-requests", status_code=202)
@limiter.limit("5/minute;20/hour")
async def file_partner_request(request: Request, payload: PartnerRequestIn, db: AsyncSession = Depends(get_db)):
    e164 = phone_or_422(payload.phone, payload.country_code)
    now = utcnow()
    await check_code(db, e164, payload.code, "partner", now)

    account = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if account is not None and "merchant" in account.role_set():
        await db.commit()
        raise HTTPException(status_code=409, detail="Ce numero est deja commercant Fidelia : connectez-vous.")
    pending = (
        await db.execute(
            select(models.PartnerRequest.id).where(
                models.PartnerRequest.phone_e164 == e164, models.PartnerRequest.status == "pending"
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        await db.commit()
        raise HTTPException(status_code=409, detail="Votre demande est deja en cours. Nous vous appelons bientot.")

    wallet = None
    if payload.wallet_provider:
        wallet = phone_or_422(payload.wallet_number, payload.country_code) if payload.wallet_number else e164
    db.add(
        models.PartnerRequest(
            phone_e164=e164, country_code=payload.country_code.upper(), contact_name=payload.contact_name.strip(), shop_name=payload.shop_name.strip(),
            category=payload.category, commune=payload.commune.strip(), address=payload.address,
            wallet_provider=payload.wallet_provider, wallet_number=wallet, notes=payload.notes,
            status="pending", created_at=now,
        )
    )
    await db.commit()
    return {
        "status": "pending",
        "message": "Demande recue. Un agent Fidelia vous appelle pour finaliser votre inscription.",
    }


@router.get("/admin/partner-requests", response_model=list[PartnerRequestOut])
async def list_partner_requests(
    status: str = "pending", db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    rows = (
        await db.execute(
            select(models.PartnerRequest)
            .where(models.PartnerRequest.status == status)
            .order_by(models.PartnerRequest.created_at)
            .limit(200)
        )
    ).scalars().all()
    return [_request_out(r) for r in rows]


# What the admin confirms before a shop asked for from the app goes live.
# "wallet_name_matches" applies only when the request names a wallet.
APPROVAL_CHECKS = {
    "called": "Appel au gerant",
    "wallet_name_matches": "Nom du titulaire du compte mobile money",
    "shop_seen": "Commerce vu (photo, position GPS ou visite)",
}


class ApproveIn(BaseModel):
    """Corrections the admin makes after the call; anything left out comes
    from the request. `checks` lists the APPROVAL_CHECKS confirmed."""

    checks: list[str] = Field(default_factory=list, max_length=8)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    commune: str | None = Field(default=None, min_length=2, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    opening_hours: str | None = Field(default=None, max_length=255)
    specialties: str | None = Field(default=None, max_length=255)
    points_per_100: int = Field(default=1, ge=0, le=20)
    note: str | None = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


async def _pending(db: AsyncSession, request_id: int) -> models.PartnerRequest:
    r = await db.get(models.PartnerRequest, request_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Partner request not found")
    if r.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {r.status}")
    return r


@router.post("/admin/partner-requests/{request_id}/approve", response_model=VenueOut)
async def approve_partner_request(
    request_id: int, payload: ApproveIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    r = await _pending(db, request_id)
    required = {"called", "shop_seen"} | ({"wallet_name_matches"} if r.wallet_number else set())
    missing = [APPROVAL_CHECKS[k] for k in APPROVAL_CHECKS if k in required - set(payload.checks)]
    if missing:
        raise HTTPException(status_code=422, detail="Verifications manquantes : " + ", ".join(missing))
    now = utcnow()
    venue = await create_venue(
        db,
        VenueIn(
            category=r.category, name=payload.name or r.shop_name, commune=payload.commune or r.commune,
            address=payload.address or r.address, opening_hours=payload.opening_hours,
            specialties=payload.specialties, points_per_100=payload.points_per_100,
            payout_provider=r.wallet_provider, payout_account=r.wallet_number,
            merchant_phone=r.phone_e164, country_code=r.country_code,
        ),
        now,
    )
    r.status, r.venue_id, r.decided_at, r.decided_by, r.decision_note = "approved", venue.id, now, admin["username"], payload.note
    r.review_checks = ",".join(k for k in APPROVAL_CHECKS if k in required)
    await db.commit()
    await _notify(r.phone_e164, f"Fidelia Pro : {venue.name} est inscrit. Connectez-vous a Fidelia Pro avec ce numero.")
    return _venue_out(venue)


@router.post("/admin/partner-requests/{request_id}/reject", response_model=PartnerRequestOut)
async def reject_partner_request(
    request_id: int, payload: RejectIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    r = await _pending(db, request_id)
    r.status, r.decided_at, r.decided_by, r.decision_note = "rejected", utcnow(), admin["username"], payload.note
    await db.commit()
    await _notify(r.phone_e164, "Fidelia Pro : votre demande d'inscription n'a pas pu etre acceptee pour l'instant. Contactez Fidelia.")
    return _request_out(r)


# --- Shops, for the admin screen ---------------------------------------------


class VenueRowOut(PublicVenueOut):
    """The customer-facing fields, plus what the admin list needs."""

    payout_provider: str | None
    has_merchant: bool
    images: int
    videos: int
    # The field agent or admin who enrolled it (full number), None for shops
    # from before attribution and for approved requests.
    enrolled_by: str | None = None


class VenueDetailAdminOut(VenueRowOut):
    payout_account: str | None
    pay_code: str | None
    # Full number: the admin calls the merchant.
    merchant_phone: str | None


class VenuePatchIn(BaseModel):
    """Only the fields sent change. Linking a merchant goes through
    `merchant_phone` so the one-number-one-shop rule holds."""

    category: Category | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)
    commune: str | None = Field(default=None, min_length=2, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    opening_hours: str | None = Field(default=None, max_length=255)
    specialties: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    points_per_100: int | None = Field(default=None, ge=0, le=20)
    payout_provider: WalletProvider | None = None
    payout_account: str | None = Field(default=None, max_length=32)
    merchant_phone: str | None = Field(default=None, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


async def _media_counts(db: AsyncSession, venue_ids: list[int]) -> dict[tuple[int, str], int]:
    if not venue_ids:
        return {}
    rows = await db.execute(
        select(models.VenueMedia.venue_id, models.VenueMedia.kind, func.count(models.VenueMedia.id))
        .where(models.VenueMedia.venue_id.in_(venue_ids), models.VenueMedia.status != "failed")
        .group_by(models.VenueMedia.venue_id, models.VenueMedia.kind)
    )
    return {(v, k): n for v, k, n in rows}


def _row(venue: models.Venue, counts: dict, cls=VenueRowOut, **extra):
    return _public_venue_out(
        venue, cls, payout_provider=venue.payout_provider, has_merchant=bool(venue.owner_username),
        images=counts.get((venue.id, "image"), 0), videos=counts.get((venue.id, "video"), 0),
        enrolled_by=venue.enrolled_by[4:] if (venue.enrolled_by or "").startswith("tel:") else venue.enrolled_by, **extra,
    )


@router.get("/admin/venues", response_model=list[VenueRowOut])
async def admin_list_venues(
    q: str | None = None, category: Category | None = None, include_samples: bool = True,
    db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin")),
):
    query = select(models.Venue).order_by(models.Venue.name).limit(300)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(models.Venue.name.ilike(like), models.Venue.commune.ilike(like)))
    if category:
        query = query.where(models.Venue.category == category)
    if not include_samples:
        query = query.where(models.Venue.is_sample.is_(False))
    venues = (await db.execute(query)).scalars().all()
    counts = await _media_counts(db, [v.id for v in venues])
    return [_row(v, counts) for v in venues]


async def _detail(db: AsyncSession, venue: models.Venue) -> VenueDetailAdminOut:
    counts = await _media_counts(db, [venue.id])
    owner = venue.owner_username or ""
    return _row(
        venue, counts, VenueDetailAdminOut, payout_account=venue.payout_account, pay_code=venue.pay_code,
        merchant_phone=owner[4:] if owner.startswith("tel:") else (owner or None),
    )


@router.get("/admin/venues/{venue_id}", response_model=VenueDetailAdminOut)
async def admin_get_venue(venue_id: int, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))):
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    return await _detail(db, venue)


@router.patch("/admin/venues/{venue_id}", response_model=VenueDetailAdminOut)
async def admin_update_venue(
    venue_id: int, payload: VenuePatchIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    changes = payload.model_dump(exclude_unset=True, exclude={"merchant_phone", "country_code", "payout_account"})
    for field_name, value in changes.items():
        setattr(venue, field_name, value.strip() if isinstance(value, str) else value)
    if "payout_account" in payload.model_fields_set:
        venue.payout_account = phone_or_422(payload.payout_account, payload.country_code) if payload.payout_account else None
    if not (venue.payout_provider and venue.payout_account):
        venue.payout_provider = venue.payout_provider if venue.payout_account else None
    elif venue.pay_code is None:
        venue.pay_code = new_pay_code()
    if payload.merchant_phone:
        await link_merchant(db, phone_or_422(payload.merchant_phone, payload.country_code), venue, utcnow())
    await db.commit()
    await db.refresh(venue)
    return await _detail(db, venue)
