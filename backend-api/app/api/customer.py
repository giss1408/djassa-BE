"""Customer-facing API: find a place to eat or shop, find an on-duty pharmacy, pay, earn points."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.security import get_current_user, require_role
from ..db import get_db
from ..schemas.customer import (
    CategoryOut,
    DealOut,
    DutyIn,
    DutyOut,
    LoyaltyConsentIn,
    LoyaltyConsentOut,
    LoyaltyEntryOut,
    LoyaltyOut,
    LoyaltyWithdrawOut,
    OnDutyPharmacyOut,
    PayCodeOut,
    PayTargetOut,
    PaymentIn,
    PaymentOut,
    RedeemIn,
    RedeemOut,
    RewardOut,
    VenueBalanceOut,
    VenueDetailOut,
    VenueOut,
)
from ..services import loyalty_consent, sale_events
from ..services.mobile_money import ProviderUnavailable, provider_for

router = APIRouter()

# Kinds of venue, in the order the app shows them: key -> (label, plural).
# French, since the app displays them as-is. A new kind of retailer is one
# line here; the app draws a generic storefront icon for keys it does not know.
CATEGORIES: dict[str, tuple[str, str]] = {
    "maquis": ("Maquis", "Maquis"),
    "superette": ("Supérette", "Supérettes"),
    "pharmacy": ("Pharmacie", "Pharmacies"),
    "mode": ("Mode", "Boutiques de mode"),
    "beaute": ("Beauté", "Salons de beauté"),
    "telephonie": ("Téléphonie", "Téléphonie"),
}
# No 0/O or 1/I: the code is read aloud across a noisy counter.
_VOUCHER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAY_CODE_LENGTH = 10  # 32^10 ~ 10^15: not guessable by trying codes


def new_pay_code() -> str:
    return "".join(secrets.choice(_VOUCHER_ALPHABET) for _ in range(PAY_CODE_LENGTH))


def qr_payload(pay_code: str) -> str:
    """The exact text encoded in a venue's payment QR code."""
    return f"djassa://pay/{pay_code}"


def _mask(account: str) -> str:
    return "\u2022\u2022\u2022\u2022" + account[-4:]


def _check_payable(venue: models.Venue) -> None:
    if not (venue.payout_provider and venue.payout_account):
        raise HTTPException(status_code=422, detail="Ce commercant n'accepte pas encore le paiement Djassa")


async def _open_request(db: AsyncSession, request: models.PaymentRequest) -> models.PaymentRequest:
    """Refuse a payment request that can no longer be paid, saying why."""
    if request.status == "open" and request.expires_at <= utcnow():
        request.status = "expired"
        await db.commit()
    detail = {
        "paid": "Ce QR code a deja ete paye",
        "processing": "Un paiement est deja en cours sur ce QR code",
        "expired": "Ce QR code a expire. Demandez-en un nouveau au commercant",
        "cancelled": "Ce QR code a ete annule par le commercant",
    }.get(request.status)
    if detail:
        raise HTTPException(status_code=409 if request.status in ("paid", "processing") else 410, detail=detail)
    return request


async def resolve_code(db: AsyncSession, code: str) -> tuple[models.Venue, models.PaymentRequest | None]:
    """A scanned code is either a merchant's one-time payment request (fixed
    amount) or a venue's static sticker (customer types the amount)."""
    code = code.strip().upper()
    request = (
        await db.execute(
            select(models.PaymentRequest)
            .options(selectinload(models.PaymentRequest.venue))
            .where(models.PaymentRequest.code == code)
        )
    ).scalar_one_or_none()
    if request is not None:
        await _open_request(db, request)
        _check_payable(request.venue)
        return request.venue, request

    venue = (await db.execute(select(models.Venue).where(models.Venue.pay_code == code))).scalar_one_or_none()
    if venue is None:
        # Same answer for "never existed" and "rotated": either way, do not pay.
        raise HTTPException(status_code=404, detail="QR code inconnu ou desactive")
    _check_payable(venue)
    return venue, None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _covers(db: AsyncSession, venue_ids: list[int]) -> dict[int, str]:
    from .media import cover_urls  # local: media imports this module's neighbours

    return await cover_urls(db, venue_ids)


async def _ready_media(db: AsyncSession, venue_id: int):
    from .media import ready_media  # local: media imports this module's neighbours

    return await ready_media(db, venue_id)


def _venue_out(venue: models.Venue, cls=VenueOut, **extra):
    data = {c: getattr(venue, c) for c in VenueOut.model_fields if hasattr(venue, c)}
    data["latitude"] = float(venue.latitude) if venue.latitude is not None else None
    data["longitude"] = float(venue.longitude) if venue.longitude is not None else None
    data["accepts_payment"] = bool(venue.payout_provider and venue.payout_account)
    return cls(**data, **extra)


def _payment_out(p: models.CustomerPayment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        venue_id=p.venue_id,
        venue_name=p.venue.name,
        amount=p.amount,
        currency=p.currency,
        wallet_provider=p.wallet_provider,
        status=p.status,
        failure_reason=p.failure_reason,
        provider_reference=p.provider_reference,
        checkout_url=p.checkout_url if p.status == "pending" else None,
        points_awarded=p.points_awarded,
        created_at=p.created_at,
        completed_at=p.completed_at,
    )


async def _balance(db: AsyncSession, customer_id: str, venue_id: int | None = None) -> int:
    q = select(func.coalesce(func.sum(models.LoyaltyEntry.points), 0)).where(
        models.LoyaltyEntry.customer_id == customer_id
    )
    if venue_id is not None:
        q = q.where(models.LoyaltyEntry.venue_id == venue_id)
    return int((await db.execute(q)).scalar_one())


# --- Discovery --------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(user=Depends(get_current_user)):
    return [CategoryOut(key=k, label=label, plural=plural) for k, (label, plural) in CATEGORIES.items()]


def live_deals_filter(moment: datetime):
    """Deals a customer may see at `moment`: switched on and within their dates."""
    return (models.Deal.active.is_(True), models.Deal.starts_at <= moment, models.Deal.ends_at > moment)


def deal_out(d: models.Deal) -> DealOut:
    return DealOut(
        id=d.id,
        venue_id=d.venue_id,
        venue_name=d.venue.name,
        venue_category=d.venue.category,
        venue_commune=d.venue.commune,
        title=d.title,
        description=d.description,
        discount_percent=d.discount_percent,
        price=d.price,
        original_price=d.original_price,
        ribbon=d.ribbon or "bon_plan",
        starts_at=d.starts_at,
        ends_at=d.ends_at,
        is_featured=d.is_featured,
        is_sample=d.venue.is_sample,
    )


@router.get("/venues", response_model=list[VenueOut])
async def list_venues(
    category: str | None = Query(None),
    q: str | None = Query(None, max_length=64),
    commune: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {tuple(CATEGORIES)}")
    stmt = select(models.Venue)
    if category:
        stmt = stmt.where(models.Venue.category == category)
    if commune:
        stmt = stmt.where(func.lower(models.Venue.commune) == commune.lower())
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(models.Venue.name).like(like),
                func.lower(models.Venue.specialties).like(like),
                func.lower(models.Venue.commune).like(like),
            )
        )
    venues = (await db.execute(stmt.order_by(models.Venue.name))).scalars().all()
    covers = await _covers(db, [v.id for v in venues])
    return [_venue_out(v, cover_url=covers.get(v.id)) for v in venues]


@router.get("/venues/{venue_id}", response_model=VenueDetailOut)
async def get_venue(venue_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    venue = (
        await db.execute(
            select(models.Venue).options(selectinload(models.Venue.rewards)).where(models.Venue.id == venue_id)
        )
    ).scalar_one_or_none()
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    rewards = [RewardOut.model_validate(r) for r in venue.rewards if r.active]
    deals = (
        await db.execute(
            select(models.Deal)
            .options(selectinload(models.Deal.venue))
            .where(models.Deal.venue_id == venue.id, *live_deals_filter(utcnow()))
            .order_by(models.Deal.ends_at)
        )
    ).scalars().all()
    return _venue_out(
        venue,
        VenueDetailOut,
        rewards=sorted(rewards, key=lambda r: r.cost_points),
        deals=[deal_out(d) for d in deals],
        my_points=await _balance(db, user["username"], venue.id),
        media=await _ready_media(db, venue.id),
        cover_url=(await _covers(db, [venue.id])).get(venue.id),
    )


@router.get("/pharmacies/on-duty", response_model=list[OnDutyPharmacyOut])
async def on_duty_pharmacies(
    commune: str | None = Query(None, max_length=64),
    at: datetime | None = Query(None, description="Defaults to now (UTC = Abidjan time)"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    moment = (at.astimezone(timezone.utc).replace(tzinfo=None) if at and at.tzinfo else at) or utcnow()
    stmt = (
        select(models.PharmacyDuty, models.Venue)
        .join(models.Venue, models.PharmacyDuty.venue_id == models.Venue.id)
        .where(
            models.Venue.category == "pharmacy",
            models.PharmacyDuty.starts_at <= moment,
            models.PharmacyDuty.ends_at > moment,
        )
    )
    if commune:
        stmt = stmt.where(func.lower(models.Venue.commune) == commune.lower())
    rows = (await db.execute(stmt.order_by(models.Venue.commune, models.Venue.name))).all()
    covers = await _covers(db, [venue.id for _, venue in rows])
    return [
        _venue_out(venue, OnDutyPharmacyOut, duty_starts_at=duty.starts_at, duty_ends_at=duty.ends_at,
                   cover_url=covers.get(venue.id))
        for duty, venue in rows
    ]


@router.post("/admin/pharmacies/{venue_id}/duties", response_model=DutyOut, status_code=201)
async def add_duty(
    venue_id: int,
    payload: DutyIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    """Record one on-duty period. The weekly rotation is entered from the
    official published list; there is no public API to pull it from."""
    venue = await db.get(models.Venue, venue_id)
    if venue is None or venue.category != "pharmacy":
        raise HTTPException(status_code=404, detail="pharmacy not found")
    starts = payload.starts_at.astimezone(timezone.utc).replace(tzinfo=None) if payload.starts_at.tzinfo else payload.starts_at
    ends = payload.ends_at.astimezone(timezone.utc).replace(tzinfo=None) if payload.ends_at.tzinfo else payload.ends_at
    if ends <= starts:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    duty = models.PharmacyDuty(venue_id=venue_id, starts_at=starts, ends_at=ends)
    db.add(duty)
    await db.commit()
    await db.refresh(duty)
    return duty


# --- Payment ----------------------------------------------------------------


@router.get("/customer/pay-codes/{code}", response_model=PayTargetOut)
async def check_pay_code(code: str, db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    """Step 1 of paying: resolve a scanned QR to the merchant it belongs to."""
    venue, request = await resolve_code(db, code)
    return PayTargetOut(
        amount=request.amount if request else None,
        expires_at=request.expires_at if request else None,
        venue_id=venue.id,
        name=venue.name,
        commune=venue.commune,
        category=venue.category,
        is_sample=venue.is_sample,
        points_per_100=venue.points_per_100,
        payout_provider=venue.payout_provider,
        payout_account_masked=_mask(venue.payout_account),
    )


@router.get("/admin/pay-codes", response_model=list[PayCodeOut])
async def list_pay_codes(db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))):
    """Everything needed to print the QR stickers."""
    venues = (
        await db.execute(select(models.Venue).where(models.Venue.pay_code.is_not(None)).order_by(models.Venue.name))
    ).scalars().all()
    return [PayCodeOut(venue_id=v.id, name=v.name, pay_code=v.pay_code, qr_payload=qr_payload(v.pay_code)) for v in venues]


@router.post("/admin/venues/{venue_id}/pay-code", response_model=PayCodeOut, status_code=201)
async def rotate_pay_code(venue_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("admin"))):
    """Issue a new code for a venue. The old QR stops working immediately:
    use it when a sticker is lost, damaged or suspected tampered."""
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    if not (venue.payout_provider and venue.payout_account):
        raise HTTPException(status_code=422, detail="venue has no payout wallet")
    venue.pay_code = new_pay_code()
    await db.commit()
    return PayCodeOut(venue_id=venue.id, name=venue.name, pay_code=venue.pay_code, qr_payload=qr_payload(venue.pay_code))


async def settle_payment(db: AsyncSession, payment: models.CustomerPayment, outcome: str, reason: str | None = None):
    """Move a pending payment to its final state, granting points once.

    Also the entry point a real aggregator's webhook will call. Settling an
    already-final payment is a no-op, so a replayed webhook cannot grant the
    points twice (the unique `payment_id` on the ledger is the second lock).

    On success this writes the `sale_event` in the same transaction that grants
    the points: one event, every view, atomically. A failed payment writes none
    -- an aggregator decline is not a sale, and the stream carries no row for it.
    """
    if payment.status != "pending":
        return
    payment.status = outcome
    payment.completed_at = utcnow()
    request = (
        await db.execute(select(models.PaymentRequest).where(models.PaymentRequest.payment_id == payment.id))
    ).scalar_one_or_none()
    if outcome == "failed":
        payment.failure_reason = reason
        if request is not None:
            # Declined by the wallet: the QR is payable again, e.g. with another wallet.
            request.status = "open"
            request.payment_id = None
        return
    if request is not None:
        request.status = "paid"
    venue = payment.venue
    # Paying in the app is not consent to loyalty: that is asked at sign-in
    # (or later, in the account screen), and can be withdrawn.
    consented = await loyalty_consent.has_consent(db, payment.customer_id)
    points = (payment.amount // 100) * (venue.points_per_100 or 0) if consented else 0
    payment.points_awarded = points
    entry = None
    if points > 0:
        entry = models.LoyaltyEntry(
            customer_id=payment.customer_id,
            venue_id=venue.id,
            points=points,
            reason="payment",
            payment_id=payment.id,
            created_at=payment.completed_at,
        )
        db.add(entry)
        # Flushed so the event can carry the entry's id: the point of the merged
        # stream is that one row links the payment, the venue and the points.
        await db.flush()
    await sale_events.record_confirmed_sale(
        db, payment=payment, loyalty_entry=entry, occurred_at=payment.completed_at
    )


@router.post("/customer/payments", response_model=PaymentOut, status_code=201)
async def pay_venue(payload: PaymentIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    existing = (
        await db.execute(
            select(models.CustomerPayment)
            .options(selectinload(models.CustomerPayment.venue))
            .where(models.CustomerPayment.idempotency_key == payload.idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.customer_id != user["username"]:
            raise HTTPException(status_code=409, detail="idempotency key already used")
        # A retry of a request whose response was lost: same payment, no new charge.
        return _payment_out(existing)

    # Re-checked here, not trusted from step 1: the code may have been
    # rotated, paid or expired between the scan and the confirmation.
    venue, request = await resolve_code(db, payload.pay_code)
    if request is not None:
        if payload.amount is not None and payload.amount != request.amount:
            raise HTTPException(status_code=409, detail="Le montant ne correspond pas a la demande du commercant")
        amount = request.amount
    else:
        if payload.amount is None:
            raise HTTPException(status_code=422, detail="Montant requis")
        amount = payload.amount

    # Chosen before anything is written: a venue that cannot take this wallet
    # is refused without leaving a pending payment or a claimed QR behind.
    try:
        provider = await provider_for(db, venue, payload.wallet_provider)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    payment = models.CustomerPayment(
        customer_id=user["username"],
        venue_id=venue.id,
        amount=amount,
        currency="XOF",
        wallet_provider=payload.wallet_provider,
        payer_msisdn=payload.payer_msisdn,
        status="pending",
        idempotency_key=payload.idempotency_key,
        created_at=utcnow(),
    )
    payment.venue = venue
    db.add(payment)
    await db.flush()
    if request is not None:
        # Claim the request atomically: of two phones confirming the same QR at
        # once, exactly one gets the row; the other is told it is taken.
        claimed = await db.execute(
            update(models.PaymentRequest)
            .where(models.PaymentRequest.id == request.id, models.PaymentRequest.status == "open")
            .values(status="processing", payment_id=payment.id)
        )
        if claimed.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Un paiement est deja en cours sur ce QR code")
    # Persist the pending row BEFORE calling out: if we crash mid-call, there is
    # a record to reconcile against the aggregator instead of a lost payment.
    await db.commit()

    result = await provider.initiate(
        amount=payment.amount,
        currency=payment.currency,
        wallet_provider=payment.wallet_provider,
        payer_msisdn=payment.payer_msisdn,
        payout_provider=venue.payout_provider,
        payout_account=venue.payout_account,
        idempotency_key=payment.idempotency_key,
    )
    payment.provider_reference = result.reference or None
    payment.checkout_url = result.launch_url
    if result.status in ("succeeded", "failed"):
        await settle_payment(db, payment, result.status, result.failure_reason)
    await db.commit()
    await db.refresh(payment)
    return _payment_out(payment)


@router.get("/customer/payments", response_model=list[PaymentOut])
async def my_payments(db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    rows = (
        await db.execute(
            select(models.CustomerPayment)
            .options(selectinload(models.CustomerPayment.venue))
            .where(models.CustomerPayment.customer_id == user["username"])
            .order_by(models.CustomerPayment.created_at.desc(), models.CustomerPayment.id.desc())
            .limit(50)
        )
    ).scalars().all()
    return [_payment_out(p) for p in rows]


@router.get("/customer/payments/{payment_id}", response_model=PaymentOut)
async def my_payment(payment_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    """One payment. A pending wallet checkout is re-read from the operator
    first, so the app can show the outcome even if the webhook is late."""
    payment = (
        await db.execute(
            select(models.CustomerPayment)
            .options(selectinload(models.CustomerPayment.venue))
            .where(models.CustomerPayment.id == payment_id, models.CustomerPayment.customer_id == user["username"])
        )
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    if payment.status == "pending" and payment.checkout_url:
        from .wave import refresh_payment  # local: app.api.wave imports this module

        await refresh_payment(db, payment)
        await db.commit()
        await db.refresh(payment)
    return _payment_out(payment)


# --- Loyalty ----------------------------------------------------------------


@router.get("/customer/loyalty", response_model=LoyaltyOut)
async def my_loyalty(db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    customer = user["username"]
    per_venue = (
        await db.execute(
            select(models.LoyaltyEntry.venue_id, func.sum(models.LoyaltyEntry.points))
            .where(models.LoyaltyEntry.customer_id == customer)
            .group_by(models.LoyaltyEntry.venue_id)
        )
    ).all()
    balances = {venue_id: int(points) for venue_id, points in per_venue}

    venues = []
    if balances:
        rows = (
            await db.execute(
                select(models.Venue)
                .options(selectinload(models.Venue.rewards))
                .where(models.Venue.id.in_(balances.keys()))
            )
        ).scalars().all()
        for v in rows:
            rewards = sorted(
                (RewardOut.model_validate(r) for r in v.rewards if r.active), key=lambda r: r.cost_points
            )
            venues.append(VenueBalanceOut(venue_id=v.id, venue_name=v.name, points=balances[v.id], rewards=rewards))
        venues.sort(key=lambda b: -b.points)

    entries = (
        await db.execute(
            select(models.LoyaltyEntry)
            .options(selectinload(models.LoyaltyEntry.venue), selectinload(models.LoyaltyEntry.reward))
            .where(models.LoyaltyEntry.customer_id == customer)
            .order_by(models.LoyaltyEntry.created_at.desc(), models.LoyaltyEntry.id.desc())
            .limit(50)
        )
    ).scalars().all()
    history = [
        LoyaltyEntryOut(
            id=e.id,
            venue_id=e.venue_id,
            venue_name=e.venue.name,
            points=e.points,
            reason=e.reason,
            voucher_code=e.voucher_code,
            reward_title=e.reward.title if e.reward else None,
            created_at=e.created_at,
        )
        for e in entries
    ]
    return LoyaltyOut(total_points=sum(balances.values()), venues=venues, history=history)


def _consent_out(row: models.LoyaltyConsent | None) -> LoyaltyConsentOut:
    if row is None:
        return LoyaltyConsentOut(active=False, current_version=loyalty_consent.CURRENT_VERSION)
    return LoyaltyConsentOut(
        active=True,
        source=row.source,
        consent_version=row.consent_version,
        granted_at=row.granted_at,
        current_version=loyalty_consent.CURRENT_VERSION,
    )


@router.get("/customer/loyalty-consent", response_model=LoyaltyConsentOut)
async def my_loyalty_consent(db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    """Whether Djassa may tie this customer's payments to their number."""
    return _consent_out(await loyalty_consent.current(db, user["username"]))


@router.put("/customer/loyalty-consent", response_model=LoyaltyConsentOut)
async def give_loyalty_consent(
    payload: LoyaltyConsentIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))
):
    """Agree to loyalty after sign-in (an account opened without it, or one
    that withdrew and changed its mind)."""
    row = await loyalty_consent.grant(
        db, user["username"], source=loyalty_consent.APP, version=payload.consent_version, now=utcnow()
    )
    await db.commit()
    return _consent_out(row)


@router.delete("/customer/loyalty-consent", response_model=LoyaltyWithdrawOut)
async def withdraw_loyalty_consent(db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    """Withdraw consent: every point is erased and past sales stop naming the
    customer. The app warns before calling this; it cannot be undone."""
    points = await loyalty_consent.withdraw(db, user["username"], utcnow())
    await db.commit()
    return LoyaltyWithdrawOut(points_erased=points)


@router.post("/customer/loyalty/redeem", response_model=RedeemOut, status_code=201)
async def redeem(payload: RedeemIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("customer"))):
    """Swap points for a reward at the venue that issued them.

    Points are per venue on purpose: a maquis funds the rewards it gives, so it
    must not pay for points earned at the pharmacy next door. There is no
    cash-out; that needs a BCEAO-licensed partner first.
    """
    reward = (
        await db.execute(
            select(models.LoyaltyReward)
            .options(selectinload(models.LoyaltyReward.venue))
            .where(models.LoyaltyReward.id == payload.reward_id)
        )
    ).scalar_one_or_none()
    if reward is None or not reward.active:
        raise HTTPException(status_code=404, detail="reward not found")

    customer = user["username"]
    balance = await _balance(db, customer, reward.venue_id)
    if balance < reward.cost_points:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"not enough points: {balance} of {reward.cost_points}",
        )

    code = "".join(secrets.choice(_VOUCHER_ALPHABET) for _ in range(6))
    db.add(
        models.LoyaltyEntry(
            customer_id=customer,
            venue_id=reward.venue_id,
            points=-reward.cost_points,
            reason="redeem",
            reward_id=reward.id,
            voucher_code=code,
            created_at=utcnow(),
        )
    )
    await db.commit()
    return RedeemOut(
        voucher_code=code,
        reward_title=reward.title,
        venue_name=reward.venue.name,
        points_spent=reward.cost_points,
        remaining_points=balance - reward.cost_points,
    )
