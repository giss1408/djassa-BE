"""Layaway: "payer en plusieurs fois" for one named good.

The customer pays for an expensive good (a phone, a fridge, school supplies)
in installments; the merchant keeps the money and hands the good over once the
price is reached. Fidelia never touches the money: it keeps the record both
sides can show, and each installment becomes evidence of saving discipline.

It is not credit and is never called credit: nothing is lent, the customer pays
first. The guardrails are what keep it ordinary commerce rather than deposit
taking (docs/business/BUSINESS-MODEL.md, layaway test):

* one named good at a price fixed when the plan is opened;
* an end date, at most `LAYAWAY_MAX_DAYS` away;
* a price cap, `LAYAWAY_MAX_PRICE`;
* terms the merchant shows and the customer accepts before anything is paid;
* no interest, no fee, no penalty.

Off by default, switched on per venue by an admin: a pilot test with a few
merchants whose goods suit it.
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.phone import PHONE_KEY_PREFIX, InvalidPhone, mask_phone, normalize_phone, phone_key
from ..core.security import SHOP_STAFF, require_role
from ..db import get_db
from ..services import sale_events
from .customer import utcnow
from .payment_requests import _my_venue

router = APIRouter()

OPEN, COMPLETED, DELIVERED, CANCELLED = "open", "completed", "delivered", "cancelled"

# Bumped whenever TERMS changes, so each plan says which wording was agreed to.
TERMS_VERSION = "tranches-2026-10"
TERMS = (
    "Vous payez {item} en plusieurs fois, au prix fixe de {price} F. "
    "L'argent va directement au commerce, pas a Fidelia. "
    "Vous recevez le produit quand le prix est atteint, au plus tard le {due_by}. "
    "Pas d'interets, pas de frais, pas de penalite. "
    "Si vous arretez ou si le commerce ne peut pas livrer, c'est le commerce qui vous rembourse."
)


def max_days() -> int:
    return int(os.getenv("LAYAWAY_MAX_DAYS", "183"))


def max_price() -> int:
    return int(os.getenv("LAYAWAY_MAX_PRICE", "1000000"))


# --- Schemas --------------------------------------------------------------------


class LayawaySettingsOut(BaseModel):
    enabled: bool
    max_days: int
    max_price: int
    terms_version: str
    terms: str


class InstallmentIn(BaseModel):
    amount: int = Field(gt=0)
    # Client-generated before the first send, reused for every retry.
    idempotency_key: str = Field(min_length=8, max_length=128)


class PlanIn(BaseModel):
    customer_phone: str = Field(min_length=8, max_length=32)
    item: str = Field(min_length=2, max_length=120)
    price: int = Field(gt=0)
    due_by: datetime
    # The version of the terms the merchant showed; refused if stale, so a plan
    # can never claim agreement to wording the customer did not see.
    terms_version: str
    terms_accepted: bool
    first_installment: InstallmentIn | None = None


class CancelIn(BaseModel):
    reason: str = Field(min_length=2, max_length=255)
    refunded_amount: int = Field(ge=0)


class LayawayToggleIn(BaseModel):
    enabled: bool


class InstallmentOut(BaseModel):
    id: int
    amount: int
    source: str
    paid_at: datetime


class PlanOut(BaseModel):
    id: int
    venue_id: int
    venue_name: str | None
    customer: str | None
    item: str
    price: int
    currency: str
    paid: int
    remaining: int
    status: str
    due_by: datetime
    created_at: datetime
    completed_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    refunded_amount: int | None
    installments: list[InstallmentOut]


class LayawaySummaryOut(BaseModel):
    """The numbers that decide whether the test continues (docs/business/KPI.md)."""

    venues_enabled: int
    plans_started: int
    by_status: dict[str, int]
    # Delivered ÷ plans that reached an end (delivered or cancelled).
    completion_rate: float | None
    overdue_open: int
    value_started: int
    value_paid: int
    median_days_to_complete: float | None
    customers: int


# --- Helpers ---------------------------------------------------------------------


def _paid(plan: models.LayawayPlan) -> int:
    return sum(i.amount for i in plan.installments)


def _customer_label(plan: models.LayawayPlan) -> str | None:
    cid = plan.customer_id or ""
    return mask_phone(cid[len(PHONE_KEY_PREFIX):]) if cid.startswith(PHONE_KEY_PREFIX) else None


def _out(plan: models.LayawayPlan) -> PlanOut:
    paid = _paid(plan)
    return PlanOut(
        id=plan.id,
        venue_id=plan.venue_id,
        venue_name=plan.venue.name if plan.venue is not None else None,
        customer=_customer_label(plan),
        item=plan.item,
        price=plan.price,
        currency=plan.currency,
        paid=paid,
        remaining=max(plan.price - paid, 0),
        status=plan.status,
        due_by=plan.due_by,
        created_at=plan.created_at,
        completed_at=plan.completed_at,
        delivered_at=plan.delivered_at,
        cancelled_at=plan.cancelled_at,
        cancel_reason=plan.cancel_reason,
        refunded_amount=plan.refunded_amount,
        installments=[
            InstallmentOut(id=i.id, amount=i.amount, source=i.source, paid_at=i.paid_at) for i in plan.installments
        ],
    )


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


async def _enabled_venue(db: AsyncSession, user) -> models.Venue:
    venue = await _my_venue(db, user, require_wallet=False)
    if not venue.layaway_enabled:
        raise HTTPException(status_code=403, detail="Le paiement en plusieurs fois n'est pas active pour ce commerce")
    return venue


async def _load(db: AsyncSession, plan_id: int, venue_id: int, lock: bool = False) -> models.LayawayPlan:
    if lock:
        # Serialise writes to one plan: two staff phones adding the last
        # installment at once must not both complete it or overpay it. A no-op
        # on SQLite (tests), a real row lock on PostgreSQL.
        await db.execute(select(models.LayawayPlan.id).where(models.LayawayPlan.id == plan_id).with_for_update())
    plan = (
        await db.execute(
            select(models.LayawayPlan)
            .options(selectinload(models.LayawayPlan.installments), selectinload(models.LayawayPlan.venue))
            .where(models.LayawayPlan.id == plan_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    # Another venue's plan is "not found", not "forbidden": its existence is
    # none of this merchant's business.
    if plan is None or plan.venue_id != venue_id:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


def _add_installment(plan: models.LayawayPlan, payload: InstallmentIn, username: str, now: datetime) -> None:
    if plan.status != OPEN:
        raise HTTPException(status_code=409, detail=f"plan is {plan.status}")
    remaining = plan.price - _paid(plan)
    if payload.amount > remaining:
        raise HTTPException(status_code=422, detail=f"Il reste {remaining} F a payer, pas plus")
    installment = models.LayawayInstallment(
        plan_id=plan.id,
        amount=payload.amount,
        source=sale_events.DECLARED,
        idempotency_key=f"layaway:{payload.idempotency_key}",
        recorded_by=username,
        paid_at=now,
    )
    plan.installments.append(installment)
    if payload.amount == remaining:
        plan.status = COMPLETED
        plan.completed_at = now


async def _find_installment(db: AsyncSession, client_key: str) -> models.LayawayInstallment | None:
    return (
        await db.execute(
            select(models.LayawayInstallment).where(
                models.LayawayInstallment.idempotency_key == f"layaway:{client_key}"
            )
        )
    ).scalar_one_or_none()


# --- Merchant ----------------------------------------------------------------------


@router.get("/merchant/layaway/settings", response_model=LayawaySettingsOut)
async def settings(db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))):
    """Whether this shop offers layaway, the limits, and the terms to show."""
    venue = await _my_venue(db, user, require_wallet=False)
    return LayawaySettingsOut(
        enabled=bool(venue.layaway_enabled),
        max_days=max_days(),
        max_price=max_price(),
        terms_version=TERMS_VERSION,
        terms=TERMS,
    )


@router.post("/merchant/layaway", response_model=PlanOut, status_code=201)
async def open_plan(payload: PlanIn, db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))):
    venue = await _enabled_venue(db, user)
    now = utcnow()
    if not payload.terms_accepted:
        raise HTTPException(status_code=422, detail="Lisez les conditions au client et cochez son accord")
    if payload.terms_version != TERMS_VERSION:
        raise HTTPException(status_code=409, detail="Les conditions ont change : mettez l'application a jour")
    if payload.price > max_price():
        raise HTTPException(status_code=422, detail=f"Prix maximum : {max_price()} F")
    due_by = _naive_utc(payload.due_by)
    if due_by <= now:
        raise HTTPException(status_code=422, detail="La date limite doit etre dans le futur")
    if due_by > now + timedelta(days=max_days()):
        raise HTTPException(status_code=422, detail=f"Duree maximum : {max_days()} jours")
    try:
        customer_id = phone_key(normalize_phone(payload.customer_phone))
    except InvalidPhone as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if payload.first_installment is not None:
        existing = await _find_installment(db, payload.first_installment.idempotency_key)
        if existing is not None:
            # A retried "open" after a dropped response: hand back the plan the
            # first attempt created rather than opening a second one.
            plan = await _load(db, existing.plan_id, venue.id)
            if plan.customer_id != customer_id or plan.item != payload.item or plan.price != payload.price:
                raise HTTPException(status_code=409, detail="Idempotency key already used")
            return _out(plan)

    plan = models.LayawayPlan(
        venue_id=venue.id,
        customer_id=customer_id,
        item=payload.item.strip(),
        price=payload.price,
        currency="XOF",
        status=OPEN,
        due_by=due_by,
        terms_version=payload.terms_version,
        created_by=user["username"],
        created_at=now,
        installments=[],
    )
    db.add(plan)
    await db.flush()
    if payload.first_installment is not None:
        _add_installment(plan, payload.first_installment, user["username"], now)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Idempotency key already used")
    return _out(await _load(db, plan.id, venue.id))


@router.get("/merchant/layaway", response_model=list[PlanOut])
async def list_plans(
    status: str | None = Query(default=None, pattern="^(open|completed|delivered|cancelled)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(*SHOP_STAFF)),
):
    venue = await _my_venue(db, user, require_wallet=False)
    query = (
        select(models.LayawayPlan)
        .options(selectinload(models.LayawayPlan.installments), selectinload(models.LayawayPlan.venue))
        .where(models.LayawayPlan.venue_id == venue.id)
        .order_by(models.LayawayPlan.created_at.desc(), models.LayawayPlan.id.desc())
        .limit(200)
    )
    if status:
        query = query.where(models.LayawayPlan.status == status)
    return [_out(p) for p in (await db.execute(query)).scalars().all()]


@router.get("/merchant/layaway/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))):
    venue = await _my_venue(db, user, require_wallet=False)
    return _out(await _load(db, plan_id, venue.id))


@router.post("/merchant/layaway/{plan_id}/installments", response_model=PlanOut, status_code=201)
async def add_installment(
    plan_id: int, payload: InstallmentIn, db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))
):
    """Record one payment towards the plan. Idempotent on `idempotency_key`."""
    venue = await _my_venue(db, user, require_wallet=False)
    existing = await _find_installment(db, payload.idempotency_key)
    if existing is not None:
        if existing.plan_id != plan_id or existing.amount != payload.amount:
            raise HTTPException(status_code=409, detail="Idempotency key already used")
        return _out(await _load(db, plan_id, venue.id))
    plan = await _load(db, plan_id, venue.id, lock=True)
    _add_installment(plan, payload, user["username"], utcnow())
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Idempotency key already used")
    return _out(await _load(db, plan_id, venue.id))


@router.post("/merchant/layaway/{plan_id}/deliver", response_model=PlanOut)
async def deliver(plan_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))):
    """The customer took the good. Only once the price is fully paid."""
    venue = await _my_venue(db, user, require_wallet=False)
    plan = await _load(db, plan_id, venue.id, lock=True)
    if plan.status == DELIVERED:
        return _out(plan)
    if plan.status != COMPLETED:
        raise HTTPException(status_code=409, detail=f"Il reste {plan.price - _paid(plan)} F a payer")
    now = utcnow()
    event = sale_events.record_layaway_sale(db, plan=plan, recorded_by=user["username"], now=now)
    await db.flush()
    plan.status = DELIVERED
    plan.delivered_at = now
    plan.sale_event_id = event.id
    await db.commit()
    return _out(await _load(db, plan_id, venue.id))


@router.post("/merchant/layaway/{plan_id}/cancel", response_model=PlanOut)
async def cancel(
    plan_id: int, payload: CancelIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))
):
    """Close a plan without handover. Owner only: it is about refunding money.

    Fidelia records what the merchant says they handed back; it moves nothing.
    """
    venue = await _my_venue(db, user, require_wallet=False)
    plan = await _load(db, plan_id, venue.id, lock=True)
    if plan.status in (DELIVERED, CANCELLED):
        raise HTTPException(status_code=409, detail=f"plan is {plan.status}")
    paid = _paid(plan)
    if payload.refunded_amount > paid:
        raise HTTPException(status_code=422, detail=f"Le client a paye {paid} F : impossible de rembourser plus")
    plan.status = CANCELLED
    plan.cancelled_at = utcnow()
    plan.cancelled_by = user["username"]
    plan.cancel_reason = payload.reason.strip()
    plan.refunded_amount = payload.refunded_amount
    await db.commit()
    return _out(await _load(db, plan_id, venue.id))


# --- Customer ------------------------------------------------------------------------


@router.get("/customer/layaway", response_model=list[PlanOut])
async def my_plans(db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    """Every plan opened on the customer's number, at any shop.

    Matched on the `tel:` key a phone + code sign-in proves, so a customer sees
    exactly the plans merchants opened for them, and nobody else's."""
    plans = (
        await db.execute(
            select(models.LayawayPlan)
            .options(selectinload(models.LayawayPlan.installments), selectinload(models.LayawayPlan.venue))
            .where(models.LayawayPlan.customer_id == user["username"])
            .order_by(models.LayawayPlan.created_at.desc(), models.LayawayPlan.id.desc())
            .limit(100)
        )
    ).scalars().all()
    return [_out(p) for p in plans]


# --- Admin -------------------------------------------------------------------------------


@router.put("/admin/venues/{venue_id}/layaway", response_model=LayawaySettingsOut)
async def toggle(
    venue_id: int, payload: LayawayToggleIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))
):
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    venue.layaway_enabled = payload.enabled
    await db.commit()
    return LayawaySettingsOut(
        enabled=payload.enabled, max_days=max_days(), max_price=max_price(), terms_version=TERMS_VERSION, terms=TERMS
    )


@router.get("/admin/layaway", response_model=LayawaySummaryOut)
async def summary(db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))):
    now = utcnow()
    plans = (
        await db.execute(select(models.LayawayPlan).options(selectinload(models.LayawayPlan.installments)))
    ).scalars().all()
    by_status: dict[str, int] = {}
    for p in plans:
        by_status[p.status] = by_status.get(p.status, 0) + 1
    ended = by_status.get(DELIVERED, 0) + by_status.get(CANCELLED, 0)
    days = sorted((p.completed_at - p.created_at).total_seconds() / 86400 for p in plans if p.completed_at)
    median = None
    if days:
        mid = len(days) // 2
        median = round(days[mid] if len(days) % 2 else (days[mid - 1] + days[mid]) / 2, 1)
    venues_enabled = (
        await db.execute(select(func.count()).select_from(models.Venue).where(models.Venue.layaway_enabled.is_(True)))
    ).scalar_one()
    return LayawaySummaryOut(
        venues_enabled=venues_enabled,
        plans_started=len(plans),
        by_status=by_status,
        completion_rate=round(by_status.get(DELIVERED, 0) / ended, 3) if ended else None,
        overdue_open=sum(1 for p in plans if p.status == OPEN and p.due_by < now),
        value_started=sum(p.price for p in plans),
        value_paid=sum(_paid(p) for p in plans),
        median_days_to_complete=median,
        customers=len({p.customer_id for p in plans}),
    )
