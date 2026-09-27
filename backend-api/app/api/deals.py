"""Deals ("bons plans"): customers browse them, merchants publish their own,
admins sell the featured slot."""

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.security import get_current_user, require_role
from ..db import get_db
from ..schemas.customer import DealFeatureIn, DealIn, DealOut
from .customer import CATEGORIES, deal_out, live_deals_filter, utcnow
from .payment_requests import _my_venue

router = APIRouter()

# A merchant cannot flood the feed: past this, end an old deal first.
MAX_LIVE_DEALS_PER_VENUE = 5


def _naive_utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


@router.get("/deals", response_model=list[DealOut])
async def list_deals(
    category: str | None = Query(None),
    commune: str | None = Query(None, max_length=64),
    featured: bool | None = Query(None, description="true: only the sponsored ones (home carousel)"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Live deals, sponsored first, then the ones ending soonest."""
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
        stmt = stmt.where(models.Deal.is_featured.is_(featured))
    stmt = stmt.order_by(models.Deal.is_featured.desc(), models.Deal.ends_at, models.Deal.id).limit(limit)
    return [deal_out(d) for d in (await db.execute(stmt)).scalars().all()]


# --- Merchant: my venue's deals ----------------------------------------------


@router.get("/merchant/deals", response_model=list[DealOut])
async def my_deals(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
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


# --- Admin: the paid featured slot --------------------------------------------


@router.patch("/admin/deals/{deal_id}/feature", response_model=DealOut)
async def feature_deal(
    deal_id: int, payload: DealFeatureIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))
):
    deal = (
        await db.execute(select(models.Deal).options(selectinload(models.Deal.venue)).where(models.Deal.id == deal_id))
    ).scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=404, detail="deal not found")
    deal.is_featured = payload.is_featured
    await db.commit()
    return deal_out(deal)
