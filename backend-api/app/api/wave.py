"""Merchants connect their own Wave Business account (pilot option B).

Fidelia never holds funds, and during the pilot has no Wave account of its own.
Two levels, the merchant's choice:

**Points only (the default, no payment key).** In THEIR Wave Business portal
(business.wave.com, Developer section) the merchant creates a webhook pointing
to the `webhook_url` Fidelia returns (`PUT /api/merchant/wave` with an empty
body creates it), with "signing secret" authentication and the
merchant.payment_received event, and pastes the signing secret into Fidelia
Pro. Every customer who pays the merchant's ordinary Wave QR then earns the
venue's points on their phone number (`tel:+225...`, the counter key) if they
agreed to loyalty in Fidelia (app/services/loyalty_consent.py); either way the
sale counts as confirmed, anonymous when they did not. The signing secret can only verify Wave's messages;
it cannot create or move a payment.

**In-app payment (optional).** The merchant also pastes an API key with ONLY
"Checkout API" access (never "Payout API": the key is a bearer secret, and
with Payout a leak could move their money out), and subscribes the webhook to
checkout.session.completed and checkout.session.payment_failed too. Customers
can then pay the shop from the Fidelia app: a Wave checkout is created with the
merchant's key and the money goes straight to the merchant's wallet.

Secrets are sealed at rest (app/core/secretbox.py) and never returned.
"""

from __future__ import annotations

import json
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models
from ..core.phone import InvalidPhone, normalize_phone, phone_key
from ..core.secretbox import SecretUnavailable, hint, seal, unseal
from ..core.security import require_role
from ..db import get_db
from ..services import loyalty_consent, sale_events, wave
from ..services.mobile_money import public_base_url
from .customer import settle_payment, utcnow
from .payment_requests import _my_venue

log = logging.getLogger(__name__)

router = APIRouter()          # mounted under /api (merchant endpoints)
public_router = APIRouter()   # mounted at the root (Wave calls these)


class WaveConnectIn(BaseModel):
    """Every field is optional and only what is sent changes: an empty body
    creates the connection and its webhook address, so the merchant has the
    address before Wave gives them the secret."""

    # Only for in-app payment. Points need no key.
    api_key: str | None = Field(default=None, min_length=16, max_length=512)
    webhook_secret: str | None = Field(default=None, min_length=8, max_length=512)


class WaveAccountOut(BaseModel):
    connected: bool
    api_key_hint: str | None = None
    # Customers can pay this shop from the Fidelia app (a key is connected).
    payments_enabled: bool = False
    webhook_configured: bool = False
    webhook_url: str | None = None
    last_event_at: str | None = None


def _webhook_url(account: models.WaveAccount) -> str:
    return f"{public_base_url()}/webhooks/wave/{account.webhook_token}"


def _out(account: models.WaveAccount | None) -> WaveAccountOut:
    if account is None:
        return WaveAccountOut(connected=False)
    return WaveAccountOut(
        connected=True,
        api_key_hint=account.api_key_hint,
        payments_enabled=account.api_key_sealed is not None,
        webhook_configured=account.webhook_secret_sealed is not None,
        webhook_url=_webhook_url(account),
        last_event_at=account.last_event_at.isoformat() if account.last_event_at else None,
    )


async def _account(db: AsyncSession, venue_id: int) -> models.WaveAccount | None:
    return (
        await db.execute(select(models.WaveAccount).where(models.WaveAccount.venue_id == venue_id))
    ).scalar_one_or_none()


@router.get("/merchant/wave", response_model=WaveAccountOut)
async def my_wave(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    return _out(await _account(db, venue.id))


@router.put("/merchant/wave", response_model=WaveAccountOut)
async def connect_wave(
    payload: WaveConnectIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))
):
    """Create or update the venue's Wave connection. A key, when given, is
    tested first with a search that moves no money, so a typo is caught here
    and not at the customer's first payment."""
    venue = await _my_venue(db, user, require_wallet=False)
    api_key = payload.api_key.strip() if payload.api_key else None
    if api_key:
        try:
            await wave.client_for(api_key).check_key()
        except wave.WaveError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = utcnow()
    account = await _account(db, venue.id)
    if account is None:
        account = models.WaveAccount(
            venue_id=venue.id,
            webhook_token=secrets.token_urlsafe(24),
            created_at=now,
        )
        db.add(account)
    if api_key:
        account.api_key_sealed = seal(api_key)
        account.api_key_hint = hint(api_key)
    if payload.webhook_secret:
        account.webhook_secret_sealed = seal(payload.webhook_secret.strip())
    account.connected_by = user["username"]
    account.updated_at = now
    # The venue is now paid in Wave; the payout fields describe where money goes.
    if not venue.payout_provider:
        venue.payout_provider = "wave"
    await db.commit()
    await db.refresh(account)
    return _out(account)


@router.delete("/merchant/wave", status_code=204)
async def disconnect_wave(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    """Forget the connection: key, secret and webhook address. The merchant should also revoke the key in
    their Wave portal; Fidelia cannot do that for them."""
    venue = await _my_venue(db, user, require_wallet=False)
    account = await _account(db, venue.id)
    if account is not None:
        await db.delete(account)
        await db.commit()
    return Response(status_code=204)


# --- Settlement ----------------------------------------------------------


async def apply_checkout(db: AsyncSession, payment: models.CustomerPayment, session: wave.CheckoutSession) -> None:
    """Settle a pending payment from what Wave says about its checkout.
    Shared by the webhook and the customer's status refresh."""
    if payment.status != "pending":
        return
    if session.succeeded:
        if session.amount is not None and session.amount != payment.amount:
            # Should never happen: the amount is fixed at creation. Do not grant
            # points on a figure we did not ask for; leave a trace to resolve.
            log.error("wave amount mismatch payment=%s asked=%s paid=%s", payment.id, payment.amount, session.amount)
            await settle_payment(db, payment, "failed", "Montant Wave different du montant demande")
            return
        payment.external_transaction_id = session.transaction_id
        await settle_payment(db, payment, "succeeded")
    elif session.failed:
        await settle_payment(db, payment, "failed", "Paiement Wave annule ou expire")


async def refresh_payment(db: AsyncSession, payment: models.CustomerPayment) -> None:
    """Ask Wave about a pending checkout (when a webhook is late or missing)."""
    if payment.status != "pending" or not payment.checkout_url or not payment.provider_reference:
        return
    account = await _account(db, payment.venue_id)
    if account is None or account.api_key_sealed is None:
        return
    try:
        session = await wave.client_for(unseal(account.api_key_sealed)).get_checkout(payment.provider_reference)
    except (wave.WaveError, SecretUnavailable) as exc:
        log.warning("wave refresh failed payment=%s: %s", payment.id, exc)
        return
    await apply_checkout(db, payment, session)


async def _payment_for(db: AsyncSession, venue_id: int, data: dict) -> models.CustomerPayment | None:
    reference = data.get("client_reference")
    if not reference:
        return None
    return (
        await db.execute(
            select(models.CustomerPayment)
            .options(selectinload(models.CustomerPayment.venue))
            .where(
                models.CustomerPayment.idempotency_key == reference,
                models.CustomerPayment.venue_id == venue_id,
            )
        )
    ).scalar_one_or_none()


def _same_phone(raw: str | None, e164: str) -> bool:
    try:
        return normalize_phone(raw or "") == e164
    except InvalidPhone:
        return False


async def _direct_payment(db: AsyncSession, account: models.WaveAccount, data: dict) -> None:
    """A payment to the merchant's Wave outside a Fidelia checkout: points on
    the sender's phone number, and a confirmed sale in the stream."""
    txn = data.get("id") or data.get("transaction_id")
    amount = wave.parse_amount(data.get("amount"))
    if not txn or amount is None or (data.get("currency") or "XOF").upper() != "XOF":
        return
    key = f"wave:{txn}"
    if (
        await db.execute(select(models.SaleEvent.id).where(models.SaleEvent.idempotency_key == key))
    ).scalar_one_or_none() is not None:
        return
    # Already counted as a Fidelia checkout payment?
    if (
        await db.execute(
            select(models.CustomerPayment.id).where(models.CustomerPayment.external_transaction_id == txn)
        )
    ).scalar_one_or_none() is not None:
        return
    try:
        sender = normalize_phone(data.get("sender_mobile") or "")
    except InvalidPhone:
        sender = None
    if sender is not None:
        # A Fidelia checkout still waiting for its own event, from this payer and
        # for this amount: that event will settle it, so do not count it twice.
        pending = (
            await db.execute(
                select(models.CustomerPayment.payer_msisdn).where(
                    models.CustomerPayment.venue_id == account.venue_id,
                    models.CustomerPayment.status == "pending",
                    models.CustomerPayment.checkout_url.is_not(None),
                    models.CustomerPayment.amount == amount,
                )
            )
        ).scalars().all()
        if any(_same_phone(p, sender) for p in pending):
            return
    # The sender's number is personal data Wave hands us without the payer
    # asking for anything: kept only if they already agreed to loyalty in
    # Fidelia. Otherwise the sale is recorded for the merchant, anonymously.
    customer_id = phone_key(sender) if sender else None
    if customer_id is not None and not await loyalty_consent.has_consent(db, customer_id):
        customer_id = None
    venue = await db.get(models.Venue, account.venue_id)
    await sale_events.record_wallet_sale(
        db,
        venue_id=venue.id,
        amount=amount,
        idempotency_key=key,
        customer_id=customer_id,
        points_per_100=venue.points_per_100,
        now=utcnow(),
    )


@public_router.post("/webhooks/wave/{token}", include_in_schema=False)
async def wave_webhook(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    account = (
        await db.execute(select(models.WaveAccount).where(models.WaveAccount.webhook_token == token))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404)
    body = await request.body()
    try:
        secret = unseal(account.webhook_secret_sealed) if account.webhook_secret_sealed else None
    except SecretUnavailable:
        secret = None
    if not secret or not wave.verify_signature(secret, request.headers.get("Wave-Signature"), body):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        event = json.loads(body)
        kind, data = event["type"], event.get("data") or {}
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="malformed event") from exc

    account.last_event_at = utcnow()
    if kind in ("checkout.session.completed", "checkout.session.payment_failed"):
        payment = await _payment_for(db, account.venue_id, data)
        if payment is not None:
            if kind == "checkout.session.payment_failed":
                reason = (data.get("last_payment_error") or {}).get("message") or "Paiement Wave refuse"
                await settle_payment(db, payment, "failed", reason[:200])
            else:
                data.setdefault("id", payment.provider_reference or "")
                await apply_checkout(db, payment, wave._session(data))
    elif kind == "merchant.payment_received":
        await _direct_payment(db, account, data)
    # Other event types are acknowledged and ignored, so Wave does not retry.
    await db.commit()
    return {"ok": True}


_RETURN_PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Fidelia</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f5132;color:#fff;display:grid;
place-items:center;min-height:100vh;margin:0;text-align:center;padding:16px}}p{{opacity:.85}}</style>
</head><body><main><h1>{title}</h1><p>{text}</p></main></body></html>"""


@public_router.get("/wave/return", include_in_schema=False, response_class=HTMLResponse)
async def wave_return(result: str = "ok"):
    """Where Wave sends the phone's browser after the payment. The app shows
    the outcome; this page only sends the customer back to it."""
    if result == "ok":
        return _RETURN_PAGE.format(title="Paiement envoye", text="Revenez dans l'application Fidelia pour voir vos points.")
    return _RETURN_PAGE.format(title="Paiement non abouti", text="Revenez dans l'application Fidelia pour reessayer.")
