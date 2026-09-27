import asyncio
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.countries import get_country
from ..core.security import get_current_user
from ..db import get_db
from ..models import Payment as PaymentModel
from ..models import PaymentDispute, PaymentRefund
from ..schemas import DisputeRequest, Payment, PaymentOut, RefundOut, RefundRequest
from ..services.payment_providers import get_payment_provider
from ..services.payment_state import PaymentStatus, transition

router = APIRouter()
PROVIDER_TIMEOUT_SECONDS = 10
PROVIDER_ATTEMPTS = 2


async def provider_call(operation):
    last_error = None
    for attempt in range(PROVIDER_ATTEMPTS):
        try:
            return await asyncio.wait_for(operation(), timeout=PROVIDER_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, OSError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 < PROVIDER_ATTEMPTS:
                await asyncio.sleep(0.1 * (attempt + 1))
    raise last_error


def payment_output(payment: PaymentModel) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        recipient_id=payment.recipient_id,
        country_code=payment.country_code,
        idempotency_key=payment.idempotency_key,
        provider=payment.provider,
        external_id=payment.external_id,
        status=payment.status,
        checkout_url=payment.checkout_url,
    )


async def owned_payment(payment_id: int, user_id: str, db: AsyncSession) -> PaymentModel:
    result = await db.execute(select(PaymentModel).where(PaymentModel.id == payment_id, PaymentModel.created_by == user_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.post("/payments", response_model=PaymentOut, status_code=201)
async def create_payment(
    payload: Payment,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    user_id = user["username"]
    profile = get_country(payload.country_code)
    if profile is None:
        raise HTTPException(status_code=422, detail="Country is not supported")
    if payload.currency.upper() != profile.currency:
        raise HTTPException(status_code=422, detail="Currency does not match country")
    key = payload.idempotency_key or idempotency_key or f"payment-{uuid.uuid4().hex}"

    existing_result = await db.execute(select(PaymentModel).where(PaymentModel.idempotency_key == key))
    existing = existing_result.scalar_one_or_none()
    if existing:
        if existing.created_by != user_id:
            raise HTTPException(status_code=409, detail="Idempotency key already used")
        return payment_output(existing)

    try:
        provider = get_payment_provider(profile.code)
        payment = PaymentModel(
            amount=payload.amount,
            currency=payload.currency.upper(),
            recipient_id=payload.recipient_id,
            country_code=profile.code,
            provider=provider.name,
            idempotency_key=key,
            status=PaymentStatus.CREATED.value,
            created_by=user_id,
        )
        db.add(payment)
        await db.flush()
        result = await provider_call(lambda: provider.initiate_payment(
            amount=payload.amount,
            currency=payload.currency.upper(),
            recipient_id=payload.recipient_id,
            idempotency_key=key,
        ))
        payment.status = transition(payment.status, PaymentStatus.PENDING)
        payment.external_id = result.external_id
        payment.provider_status = result.status
        payment.checkout_url = result.checkout_url
        await db.commit()
        await db.refresh(payment)
        return payment_output(payment)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=502, detail="Payment provider unavailable")


@router.get("/payments/{payment_id}", response_model=PaymentOut)
async def get_payment(payment_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    payment = await owned_payment(payment_id, user["username"], db)
    return payment_output(payment)


@router.post("/payments/{payment_id}/refunds", response_model=RefundOut, status_code=201)
async def refund_payment(payment_id: int, payload: RefundRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    payment = await owned_payment(payment_id, user["username"], db)
    if payment.status != PaymentStatus.SUCCEEDED.value:
        raise HTTPException(status_code=409, detail="Only succeeded payments can be refunded")
    existing_result = await db.execute(select(PaymentRefund).where(PaymentRefund.idempotency_key == payload.idempotency_key))
    existing = existing_result.scalar_one_or_none()
    if existing:
        return RefundOut(id=existing.id, payment_id=existing.payment_id, amount=existing.amount, external_id=existing.external_id, status=existing.status)
    amount = payload.amount or payment.amount
    if amount > payment.amount:
        raise HTTPException(status_code=422, detail="Refund exceeds payment amount")
    provider = get_payment_provider(payment.country_code)
    refund = PaymentRefund(payment_id=payment.id, amount=amount, idempotency_key=payload.idempotency_key, status="pending")
    db.add(refund)
    payment.status = transition(payment.status, PaymentStatus.REFUND_PENDING)
    await db.flush()
    try:
        result = await provider_call(lambda: provider.refund(external_id=payment.external_id, amount=amount, idempotency_key=payload.idempotency_key))
        refund.external_id = result.external_id
        refund.status = result.status
        await db.commit()
        await db.refresh(refund)
        return RefundOut(id=refund.id, payment_id=refund.payment_id, amount=refund.amount, external_id=refund.external_id, status=refund.status)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=502, detail="Refund provider unavailable")


@router.post("/payments/{payment_id}/disputes", status_code=201)
async def open_payment_dispute(payment_id: int, payload: DisputeRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    payment = await owned_payment(payment_id, user["username"], db)
    if payment.status not in {PaymentStatus.PENDING.value, PaymentStatus.SUCCEEDED.value}:
        raise HTTPException(status_code=409, detail="Payment cannot be disputed in its current state")
    dispute = PaymentDispute(payment_id=payment.id, reason=payload.reason, status="open")
    db.add(dispute)
    payment.status = transition(payment.status, PaymentStatus.DISPUTED)
    await db.commit()
    return {"id": dispute.id, "payment_id": payment.id, "status": dispute.status}
