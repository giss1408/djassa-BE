from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_db
from ..models import Payment as PaymentModel, PaymentReconciliation, WebhookEvent, WebhookIdempotency
from ..services.payment_state import PaymentStatus, transition
from ..schemas.webhook import WebhookIn
from ..rate_limiter import limiter
import hmac
import hashlib
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import os
REPLAY_WINDOW_SECONDS = int(os.getenv("WEBHOOK_REPLAY_WINDOW", "300"))
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("WEBHOOK_IDEMPOTENCY_TTL", "86400"))

# key rotation support: secrets are stored as comma-separated versions in env var
def load_active_and_previous_keys(env_var_name: str):
    raw = os.getenv(env_var_name, "")
    if not raw:
        return []
    # newest first
    return [k for k in [s.strip() for s in raw.split(",")] if k]

def verify_signature_with_rotation(raw_body: bytes, signature: str, keys: list) -> bool:
    if not signature or not keys:
        return False
    for key in keys:
        mac = hmac.new(key.encode(), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(mac, signature):
            return True
    return False

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    if not signature:
        return False
    mac = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature)


@router.post("/mobile-money")
@limiter.limit("10/minute")
async def mobile_money_webhook(
    request: Request,
    x_signature: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid json payload")

    # Secret rotation: `MOBILE_MONEY_SECRETS` contains comma-separated keys (latest first)
    keys = load_active_and_previous_keys("MOBILE_MONEY_SECRETS")

    ok = verify_signature_with_rotation(raw, x_signature or "", keys)
    if not ok:
        raise HTTPException(status_code=401, detail="invalid signature")

    # idempotency: check unique external_id
    external_id = payload.get("transaction_id") or payload.get("id")
    if not external_id:
        raise HTTPException(status_code=400, detail="missing transaction id")

    # Replay protection is mandatory for signed payment events.
    ts = payload.get("timestamp")
    if not ts or not isinstance(ts, str):
        raise HTTPException(status_code=400, detail="missing timestamp")
    try:
        ev_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ev_time.tzinfo is None:
            ev_time = ev_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if abs((now - ev_time).total_seconds()) > REPLAY_WINDOW_SECONDS:
            raise HTTPException(status_code=400, detail="replay window exceeded")
    except HTTPException:
        raise
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid timestamp")

    # check idempotency record; expired markers should be ignored
    existing = await db.get(WebhookIdempotency, external_id)
    if existing:
        # check TTL
        if existing.created_at and (datetime.utcnow() - existing.created_at).total_seconds() < IDEMPOTENCY_TTL_SECONDS:
            return {"status": "already_processed"}
        # else consider expired and allow reprocessing

    # persist idempotency marker and event (created_at set by DB default)
    marker = WebhookIdempotency(external_id=external_id)
    event = WebhookEvent(payload=json.dumps(payload), external_id=external_id)
    db.add(marker)
    db.add(event)
    try:
        await db.commit()
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError
        if not isinstance(exc, IntegrityError):
            raise
        await db.rollback()
        return {"status": "already_processed"}

    # Enqueue async processing via Celery
    try:
        from ..celery_tasks import send_webhook_processing_event
        send_webhook_processing_event.delay(external_id)
    except Exception:
        # fallback: process inline
        from ..services import tontine
        await tontine.process_webhook(external_id)

    # Reconcile a matching payment intent when the provider includes status,
    # amount, and currency. Business settlement remains provider-specific.
    payment_result = await db.execute(select(PaymentModel).where(PaymentModel.external_id == str(external_id)))
    payment = payment_result.scalar_one_or_none()
    provider_status = str(payload.get("status", "")).lower()
    if payment and provider_status in {"succeeded", "failed", "cancelled", "disputed"}:
        try:
            callback_amount = payload.get("amount")
            callback_currency = str(payload.get("currency", "")).upper()
            try:
                callback_amount_value = Decimal(str(callback_amount))
            except (InvalidOperation, TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid payment amount")
            if callback_currency != payment.currency or callback_amount_value != payment.amount:
                raise HTTPException(status_code=400, detail="payment amount or currency mismatch")
            target = PaymentStatus(provider_status)
            payment.status = transition(payment.status, target)
            payment.provider_status = provider_status
            db.add(PaymentReconciliation(
                payment_id=payment.id,
                external_id=str(external_id),
                provider=payment.provider,
                provider_status=provider_status,
                amount=callback_amount_value,
                currency=payment.currency,
                raw_reference=str(payload.get("reference", ""))[:255] or None,
            ))
            await db.commit()
        except HTTPException:
            await db.rollback()
            raise
        except ValueError:
            await db.rollback()

    return {"status": "accepted"}
