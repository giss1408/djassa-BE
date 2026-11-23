"""The pilot scorecard: one page that answers the Phase 1 gate, merchant by merchant.

The pilot asks three questions (docs/business/CONCEPT.md § 12): do merchants
keep recording, does the customer app bring them customers, and will they pay?
Most of the answer is already in the platform. What it cannot know, the team
records by hand on each pilot merchant (`PilotMerchant`):

    GET /api/admin/venues/{id}/pilot     the merchant's pilot record
    PUT /api/admin/venues/{id}/pilot     baseline, self-declared gender, day-45 commitment
    GET /api/admin/pilot/scorecard       every pilot merchant, side by side

The scorecard reports **counts next to every rate**. With 5 to 10 merchants one
merchant moves a percentage by 10 to 20 points, so a rate without its "n of N"
is a number that cannot be read (docs/business/KPI.md § 3.5).
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.security import require_role
from ..db import get_db
from .customer import utcnow
from .usage_events import daily_estimate, recorded_share, sales_per_day

router = APIRouter()

Gender = Literal["woman", "man", "undisclosed"]
Commitment = Literal["committed", "declined", "undecided"]
# The plans a merchant can commit to when the pilot ends (BUSINESS-MODEL.md § Pricing experiment).
CommitPlan = Literal["starter", "growth", "network"]


class PilotIn(BaseModel):
    """Only the fields sent change; send null to clear one."""

    baseline_tickets_per_day: int | None = Field(default=None, ge=0, le=10_000)
    baseline_average_basket: int | None = Field(default=None, ge=0, le=10_000_000)
    baseline_mobile_money_pct: int | None = Field(default=None, ge=0, le=100)
    baseline_repeat_pct: int | None = Field(default=None, ge=0, le=100)
    owner_gender: Gender | None = None
    commitment: Commitment | None = None
    commitment_plan: CommitPlan | None = None
    commitment_price: int | None = Field(default=None, ge=0, le=1_000_000)
    notes: str | None = Field(default=None, max_length=2000)


BASELINE_FIELDS = ("baseline_tickets_per_day", "baseline_average_basket", "baseline_mobile_money_pct", "baseline_repeat_pct")
COMMITMENT_FIELDS = ("commitment", "commitment_plan", "commitment_price")


class PilotOut(BaseModel):
    venue_id: int
    in_pilot: bool
    baseline_recorded_at: datetime | None
    baseline_tickets_per_day: int | None
    baseline_average_basket: int | None
    baseline_mobile_money_pct: int | None
    baseline_repeat_pct: int | None
    # False when the first baseline figure was recorded after the merchant's
    # first sale: the "before" is then partly an "after", and the lift is weak.
    baseline_before_first_sale: bool | None
    owner_gender: str | None
    commitment: str | None
    commitment_plan: str | None
    commitment_price: int | None
    commitment_at: datetime | None
    notes: str | None
    updated_by: str | None
    updated_at: datetime | None


async def _venue(db: AsyncSession, venue_id: int) -> models.Venue:
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue


async def _record(db: AsyncSession, venue_id: int) -> models.PilotMerchant | None:
    return (
        await db.execute(select(models.PilotMerchant).where(models.PilotMerchant.venue_id == venue_id))
    ).scalar_one_or_none()


async def _first_sales(db: AsyncSession, venue_ids: list[int]) -> dict[int, datetime]:
    if not venue_ids:
        return {}
    S = models.SaleEvent
    rows = await db.execute(
        select(S.venue_id, func.min(S.occurred_at)).where(S.venue_id.in_(venue_ids), S.status == "recorded").group_by(S.venue_id)
    )
    return dict(rows.all())


def _before_first_sale(record: models.PilotMerchant | None, first_sale: datetime | None) -> bool | None:
    if record is None or record.baseline_recorded_at is None:
        return None
    return first_sale is None or record.baseline_recorded_at <= first_sale


def _out(venue_id: int, record: models.PilotMerchant | None, first_sale: datetime | None) -> PilotOut:
    fields = {
        name: getattr(record, name) if record else None
        for name in PilotOut.model_fields
        if name not in ("venue_id", "in_pilot", "baseline_before_first_sale")
    }
    return PilotOut(
        venue_id=venue_id, in_pilot=record is not None,
        baseline_before_first_sale=_before_first_sale(record, first_sale), **fields,
    )


async def forget_owner(db: AsyncSession, venue_id: int) -> None:
    """The shop has a new owner: the previous owner's self-declared gender is
    theirs, not the shop's, so it goes. The caller commits."""
    record = await _record(db, venue_id)
    if record is not None:
        record.owner_gender = None


@router.get("/admin/venues/{venue_id}/pilot", response_model=PilotOut)
async def get_pilot(venue_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_role("admin"))):
    await _venue(db, venue_id)
    first = (await _first_sales(db, [venue_id])).get(venue_id)
    return _out(venue_id, await _record(db, venue_id), first)


@router.put("/admin/venues/{venue_id}/pilot", response_model=PilotOut)
async def put_pilot(
    venue_id: int, payload: PilotIn, db: AsyncSession = Depends(get_db), admin=Depends(require_role("admin"))
):
    """Puts the venue in the pilot on first call. The baseline date is set by
    the server the first time a baseline figure arrives, never by the client:
    it is what proves the baseline came before the first sale."""
    venue = await _venue(db, venue_id)
    if venue.is_sample:
        raise HTTPException(status_code=422, detail="Un commerce d'exemple ne fait pas partie du pilote")
    now = utcnow()
    record = await _record(db, venue_id)
    if record is None:
        record = models.PilotMerchant(venue_id=venue_id, updated_by=admin["username"], updated_at=now)
        db.add(record)
    sent = payload.model_fields_set
    for name in sent:
        setattr(record, name, getattr(payload, name))
    if record.baseline_recorded_at is None and any(getattr(record, f) is not None for f in BASELINE_FIELDS):
        record.baseline_recorded_at = now
    if sent & set(COMMITMENT_FIELDS):
        record.commitment_at = now if record.commitment else None
    if record.commitment == "committed" and not (record.commitment_plan and record.commitment_price):
        raise HTTPException(status_code=422, detail="Un engagement indique la formule et le prix acceptes")
    record.updated_by, record.updated_at = admin["username"], now
    await db.commit()
    first = (await _first_sales(db, [venue_id])).get(venue_id)
    return _out(venue_id, record, first)


# --- The scorecard ------------------------------------------------------------


class ScorecardRow(BaseModel):
    venue_id: int
    venue_name: str
    category: str
    commune: str
    owner_gender: str | None
    first_sale_at: datetime | None
    days_since_first_sale: int | None
    # North Star: share of real sales recorded, over the days the merchant gave
    # an end-of-day estimate in the window.
    recorded_share: float | None
    daily_reports: int
    # Repeat visits of identified customers (a phone number on the sale):
    # customers with sales on 2+ different days in the window ÷ customers seen.
    identified_customers: int
    returning_customers: int
    repeat_pct: int | None
    baseline_repeat_pct: int | None
    repeat_lift_pts: int | None
    baseline_before_first_sale: bool | None
    # Offers used at the counter in the window, and how many were first visits.
    offer_uses: int
    new_customers_from_offers: int
    commitment: str | None
    commitment_plan: str | None
    commitment_price: int | None


class ScorecardOut(BaseModel):
    days: int
    since: datetime
    merchants: int
    women: int
    with_baseline: int
    recording_70: int  # merchants at or above the day-30 target of 70% recorded
    recording_85: int  # ... and at or above the day-60 target of 85%
    with_new_customers: int
    committed: int
    declined: int
    rows: list[ScorecardRow]


@router.get("/admin/pilot/scorecard", response_model=ScorecardOut)
async def scorecard(
    days: int = Query(default=30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("admin")),
):
    """Every venue with a pilot record, with the window's figures.

    Aggregated in Python, like the usage summary: pilot volumes are small, and
    it keeps the JSON props portable between SQLite (tests) and Postgres."""
    now = utcnow()
    since = now - timedelta(days=days)
    pairs = (
        await db.execute(
            select(models.PilotMerchant, models.Venue)
            .join(models.Venue, models.Venue.id == models.PilotMerchant.venue_id)
            .order_by(models.Venue.name)
        )
    ).all()
    ids = [venue.id for _, venue in pairs]
    first_sales = await _first_sales(db, ids)
    sales = await sales_per_day(db, ids, since) if ids else {}

    estimates: dict[int, dict[date, int]] = defaultdict(dict)
    if ids:
        E = models.UsageEvent
        reports = await db.execute(
            select(E).where(E.app == "retailer", E.name == "daily_report", E.venue_id.in_(ids), E.occurred_at >= since)
        )
        for row in reports.scalars():
            if (value := daily_estimate(row)) is not None:
                estimates[row.venue_id][row.occurred_at.date()] = value

    visit_days: dict[int, dict[str, set[date]]] = defaultdict(lambda: defaultdict(set))
    if ids:
        S = models.SaleEvent
        for venue_id, customer, occurred in (
            await db.execute(
                select(S.venue_id, S.customer_id, S.occurred_at).where(
                    S.venue_id.in_(ids), S.customer_id.is_not(None), S.status == "recorded", S.occurred_at >= since
                )
            )
        ).all():
            visit_days[venue_id][customer].add(occurred.date())

    uses: dict[int, list[bool]] = defaultdict(list)
    if ids:
        U = models.DealUse
        for venue_id, new in (
            await db.execute(select(U.venue_id, U.new_customer).where(U.venue_id.in_(ids), U.created_at >= since))
        ).all():
            uses[venue_id].append(new)

    rows = []
    for record, venue in pairs:
        customers = visit_days[venue.id]
        returning = sum(1 for d in customers.values() if len(d) >= 2)
        repeat = round(100 * returning / len(customers)) if customers else None
        first = first_sales.get(venue.id)
        rows.append(
            ScorecardRow(
                venue_id=venue.id, venue_name=venue.name, category=venue.category, commune=venue.commune,
                owner_gender=record.owner_gender, first_sale_at=first,
                days_since_first_sale=(now - first).days if first else None,
                recorded_share=recorded_share(estimates[venue.id], sales.get(venue.id, {})),
                daily_reports=len(estimates[venue.id]),
                identified_customers=len(customers), returning_customers=returning, repeat_pct=repeat,
                baseline_repeat_pct=record.baseline_repeat_pct,
                repeat_lift_pts=repeat - record.baseline_repeat_pct
                if repeat is not None and record.baseline_repeat_pct is not None
                else None,
                baseline_before_first_sale=_before_first_sale(record, first),
                offer_uses=len(uses[venue.id]), new_customers_from_offers=sum(uses[venue.id]),
                commitment=record.commitment, commitment_plan=record.commitment_plan,
                commitment_price=record.commitment_price,
            )
        )

    return ScorecardOut(
        days=days, since=since, merchants=len(rows),
        women=sum(1 for r in rows if r.owner_gender == "woman"),
        with_baseline=sum(1 for r in rows if r.baseline_repeat_pct is not None),
        recording_70=sum(1 for r in rows if r.recorded_share is not None and r.recorded_share >= 0.70),
        recording_85=sum(1 for r in rows if r.recorded_share is not None and r.recorded_share >= 0.85),
        with_new_customers=sum(1 for r in rows if r.new_customers_from_offers > 0),
        committed=sum(1 for r in rows if r.commitment == "committed"),
        declined=sum(1 for r in rows if r.commitment == "declined"),
        rows=rows,
    )
