"""Deals ("bons plans"): customers browse them, merchants publish their own,
admins sell the featured slot."""

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.security import SHOP_STAFF, require_role
from ..db import get_db
from ..rate_limiter import limiter, public_read_limit
from ..schemas.customer import DealIn, DealOut, PlacementIn, PlacementOut, PlacementPaidIn
from .customer import CATEGORIES, deal_out, live_deals_filter, utcnow
from .payment_requests import _my_venue

router = APIRouter()

# A merchant cannot flood the feed: past this, end an old deal first.
MAX_LIVE_DEALS_PER_VENUE = 5

# How many deals may hold the carousel for the same commune+category window.
# Scarcity is what makes the slot worth buying, so the limit is the product,
# not a technical cap: raising it devalues every placement already sold.
FEATURED_SLOTS_PER_SEGMENT = 2


def _naive_utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


@router.get("/deals", response_model=list[DealOut])
@limiter.limit(public_read_limit)
async def list_deals(
    request: Request,
    category: str | None = Query(None),
    commune: str | None = Query(None, max_length=64),
    featured: bool | None = Query(None, description="true: only the sponsored ones (home carousel)"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Live deals, sponsored first, then the ones ending soonest. Public: the
    customer app shows them before any sign-in."""
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {tuple(CATEGORIES)}")
    stmt = (
        select(models.Deal)
        .join(models.Venue, models.Deal.venue_id == models.Venue.id)
        .options(selectinload(models.Deal.venue))
        .where(*live_deals_filter(utcnow()))
    )
    if category:
        stmt = stmt.where(models.Venue.category == category)
    if commune:
        stmt = stmt.where(func.lower(models.Venue.commune) == commune.lower())
    if featured is not None:
        # Sponsored means "has a placement live right now", not "someone once
        # set the flag": an expired campaign must leave the carousel even if the
        # expiry sweep has not run yet.
        live_placement = select(models.DealPlacement.deal_id).where(*live_placements_filter(utcnow()))
        stmt = stmt.where(models.Deal.id.in_(live_placement) if featured else models.Deal.id.not_in(live_placement))
    stmt = stmt.order_by(models.Deal.is_featured.desc(), models.Deal.ends_at, models.Deal.id).limit(limit)
    return [deal_out(d) for d in (await db.execute(stmt)).scalars().all()]


# --- Merchant: my venue's deals ----------------------------------------------


@router.get("/merchant/deals", response_model=list[DealOut])
async def my_deals(db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))):
    venue = await _my_venue(db, user, require_wallet=False)
    rows = (
        await db.execute(
            select(models.Deal)
            .options(selectinload(models.Deal.venue))
            .where(models.Deal.venue_id == venue.id, models.Deal.active.is_(True))
            .order_by(models.Deal.ends_at.desc())
        )
    ).scalars().all()
    return [deal_out(d) for d in rows]


@router.post("/merchant/deals", response_model=DealOut, status_code=201)
async def create_deal(payload: DealIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    now = utcnow()
    starts = _naive_utc(payload.starts_at) if payload.starts_at else now
    ends = _naive_utc(payload.ends_at)
    if ends <= max(starts, now):
        raise HTTPException(status_code=422, detail="La date de fin doit etre dans le futur et apres le debut")
    if not (payload.discount_percent or payload.price is not None):
        raise HTTPException(status_code=422, detail="Indiquez une reduction ou un prix promo")
    live = (
        await db.execute(
            select(func.count(models.Deal.id)).where(models.Deal.venue_id == venue.id, *live_deals_filter(now))
        )
    ).scalar_one()
    if live >= MAX_LIVE_DEALS_PER_VENUE:
        raise HTTPException(status_code=409, detail=f"Maximum {MAX_LIVE_DEALS_PER_VENUE} bons plans en cours")
    deal = models.Deal(
        venue_id=venue.id,
        title=payload.title.strip(),
        description=payload.description,
        discount_percent=payload.discount_percent,
        price=payload.price,
        original_price=payload.original_price,
        ribbon=payload.ribbon,
        starts_at=starts,
        ends_at=ends,
        is_featured=False,  # never self-granted, see Deal
        active=True,
        created_at=now,
    )
    deal.venue = venue
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return deal_out(deal)


@router.delete("/merchant/deals/{deal_id}", status_code=204)
async def end_deal(deal_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    """End a deal now. Kept in the table (inactive) for the record."""
    venue = await _my_venue(db, user, require_wallet=False)
    deal = await db.get(models.Deal, deal_id)
    if deal is None or deal.venue_id != venue.id:
        raise HTTPException(status_code=404, detail="deal not found")
    deal.active = False
    await db.commit()


# --- Admin: selling the featured slot -----------------------------------------


def live_placements_filter(moment):
    """Placements putting their deal in the carousel at `moment`."""
    return (
        models.DealPlacement.status == "active",
        models.DealPlacement.starts_at <= moment,
        models.DealPlacement.ends_at > moment,
    )


def _placement_out(p: models.DealPlacement, now=None) -> PlacementOut:
    now = now or utcnow()
    return PlacementOut(
        id=p.id,
        deal_id=p.deal_id,
        venue_id=p.venue_id,
        venue_name=p.venue.name,
        deal_title=p.deal.title,
        starts_at=p.starts_at,
        ends_at=p.ends_at,
        price=p.price,
        currency=p.currency,
        status=p.status,
        paid_at=p.paid_at,
        payment_reference=p.payment_reference,
        created_by=p.created_by,
        created_at=p.created_at,
        is_live=p.status == "active" and p.starts_at <= now < p.ends_at,
    )


async def _load_placement(db: AsyncSession, placement_id: int) -> models.DealPlacement:
    p = (
        await db.execute(
            select(models.DealPlacement)
            .options(selectinload(models.DealPlacement.venue), selectinload(models.DealPlacement.deal))
            .where(models.DealPlacement.id == placement_id)
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="placement not found")
    return p


async def refresh_featured_flags(db: AsyncSession, now=None) -> int:
    """Make `Deal.is_featured` agree with the placements, and expire past runs.

    The apps read the boolean, so it stays; this is what keeps it honest. Called
    after every placement change and by the periodic sweep, so a slot leaves the
    carousel on its own when its window closes. Returns how many placements were
    expired, for the sweep to log.
    """
    now = now or utcnow()
    expired = await db.execute(
        update(models.DealPlacement)
        .where(models.DealPlacement.status == "active", models.DealPlacement.ends_at <= now)
        .values(status="expired")
    )
    live = select(models.DealPlacement.deal_id).where(*live_placements_filter(now))
    await db.execute(update(models.Deal).where(models.Deal.id.in_(live)).values(is_featured=True))
    await db.execute(
        update(models.Deal).where(models.Deal.id.not_in(live), models.Deal.is_featured.is_(True)).values(is_featured=False)
    )
    return expired.rowcount or 0


@router.post("/admin/deals/{deal_id}/placements", response_model=PlacementOut, status_code=201)
async def sell_placement(
    deal_id: int, payload: PlacementIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))
):
    """Sell the featured slot to a deal for a dated window.

    Admin-only, like the flag it replaces: placement is sold, never self-granted.
    """
    deal = (
        await db.execute(select(models.Deal).options(selectinload(models.Deal.venue)).where(models.Deal.id == deal_id))
    ).scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=404, detail="deal not found")

    now = utcnow()
    starts = _naive_utc(payload.starts_at) if payload.starts_at else now
    ends = _naive_utc(payload.ends_at)
    if ends <= max(starts, now):
        raise HTTPException(status_code=422, detail="La fin de la campagne doit etre dans le futur et apres le debut")
    # Selling a window the deal itself does not cover would bill for days the
    # carousel could never show it.
    if starts < deal.starts_at or ends > deal.ends_at:
        raise HTTPException(status_code=422, detail="La campagne doit tenir dans les dates du bon plan")

    # Scarcity check, on the segment the customer actually browses.
    overlapping = (
        await db.execute(
            select(func.count(models.DealPlacement.id))
            .join(models.Deal, models.DealPlacement.deal_id == models.Deal.id)
            .join(models.Venue, models.Deal.venue_id == models.Venue.id)
            .where(
                models.DealPlacement.status.in_(("reserved", "active")),
                models.DealPlacement.starts_at < ends,
                models.DealPlacement.ends_at > starts,
                func.lower(models.Venue.commune) == deal.venue.commune.lower(),
                models.Venue.category == deal.venue.category,
            )
        )
    ).scalar_one()
    if overlapping >= FEATURED_SLOTS_PER_SEGMENT:
        raise HTTPException(
            status_code=409,
            detail=f"Les {FEATURED_SLOTS_PER_SEGMENT} emplacements sponsorises de ce segment sont deja vendus sur cette periode",
        )

    placement = models.DealPlacement(
        deal_id=deal.id,
        venue_id=deal.venue_id,
        starts_at=starts,
        ends_at=ends,
        price=payload.price,
        currency=payload.currency,
        status="active",
        created_by=user["username"],
        created_at=now,
    )
    placement.deal = deal
    placement.venue = deal.venue
    db.add(placement)
    await db.flush()
    await refresh_featured_flags(db, now)
    await db.commit()
    await db.refresh(placement)
    return _placement_out(await _load_placement(db, placement.id), now)


@router.get("/admin/placements", response_model=list[PlacementOut])
async def list_placements(
    status_filter: str | None = Query(None, alias="status"),
    unpaid: bool | None = Query(None, description="true: sold but not settled yet"),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    """What is sold, running, expiring and still owed."""
    now = utcnow()
    await refresh_featured_flags(db, now)
    await db.commit()
    stmt = select(models.DealPlacement).options(
        selectinload(models.DealPlacement.venue), selectinload(models.DealPlacement.deal)
    )
    if status_filter:
        stmt = stmt.where(models.DealPlacement.status == status_filter)
    if unpaid is not None:
        stmt = stmt.where(models.DealPlacement.paid_at.is_(None) if unpaid else models.DealPlacement.paid_at.is_not(None))
    stmt = stmt.order_by(models.DealPlacement.starts_at.desc(), models.DealPlacement.id.desc()).limit(limit)
    return [_placement_out(p, now) for p in (await db.execute(stmt)).scalars().all()]


@router.post("/admin/placements/{placement_id}/paid", response_model=PlacementOut)
async def record_placement_payment(
    placement_id: int,
    payload: PlacementPaidIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    """Record that the merchant settled, out of band (pilot reality).

    Idempotent: recording twice keeps the first settlement, so a double click
    cannot rewrite the reference of a payment already on the books.
    """
    placement = await _load_placement(db, placement_id)
    if placement.paid_at is None:
        placement.paid_at = utcnow()
        placement.payment_reference = payload.payment_reference
        await db.commit()
    return _placement_out(placement)


@router.post("/admin/placements/{placement_id}/cancel", response_model=PlacementOut)
async def cancel_placement(placement_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))):
    """Pull a campaign. The row stays, for the books."""
    placement = await _load_placement(db, placement_id)
    if placement.status in ("reserved", "active"):
        placement.status = "cancelled"
        await db.flush()
        await refresh_featured_flags(db)
        await db.commit()
        await db.refresh(placement)
    return _placement_out(placement)
