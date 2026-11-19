"""Changing where a shop's customer payments are paid out: the wallet-change process.

Why it exists: the wallet is the destination of the shop's money, so a stolen password must not be enough to redirect it, and
an agent's typo or fraud must not either. The merchant enters the wallet himself in Fidelia Pro (never at enrolment) and:

  1. REQUEST      the merchant re-enters his password (step-up at auth) -> pending_confirmation. The current wallet keeps working.
  2. CODE         an admin sends a WhatsApp message to the merchant's LOGIN number through a wa.me link (shop, masked new wallet, a
                  6-digit code), the same relay as sign-in codes.
  3. CONFIRMATION the merchant types the code -> confirmed_waiting, and a 24 h delay starts (no delay for a FIRST wallet).
  4. ACTIVATION   after the delay the new wallet replaces the old one, applied the next time the shop is used or looked at.
  Exits: "this wasn't me" at any time before activation freezes the change and alerts the admins; an admin can call the merchant
  and activate at once with a written call note (audited, counted: 3 or more a day by one admin raises an alert); an admin can
  reject. Every step is written to wallet_change_events.
  A newly activated wallet is capped for its first week (default 50,000 XOF received in total), even after an immediate activation.

Settings (environment): WALLET_CHANGE_DELAY_HOURS=24, WALLET_NEW_CAP_XOF=50000, WALLET_NEW_CAP_DAYS=7, WALLET_FAST_PATH_ALERT_PER_DAY=3.
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.security import SECRET_KEY
from . import admin_alerts

CODE_TTL = timedelta(hours=48)
MAX_CODE_ATTEMPTS = 5
OPEN_STATES = ("pending_confirmation", "confirmed_waiting", "frozen")


def _now() -> datetime:
    return datetime.utcnow()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def delay() -> timedelta:
    return timedelta(hours=_env_int("WALLET_CHANGE_DELAY_HOURS", 24))


def cap_xof() -> int:
    return _env_int("WALLET_NEW_CAP_XOF", 50000)


def cap_window() -> timedelta:
    return timedelta(days=_env_int("WALLET_NEW_CAP_DAYS", 7))


def fast_path_alert_threshold() -> int:
    return _env_int("WALLET_FAST_PATH_ALERT_PER_DAY", 3)


def mask(account: str | None) -> str | None:
    return None if not account else "••••" + account[-4:]


def wa_link(phone_e164: str, text: str) -> str:
    return f"https://wa.me/{phone_e164.lstrip('+')}?text={quote(text)}"


def _hash(change_id: int, code: str) -> str:
    return hmac.new(SECRET_KEY.encode(), f"wallet-change:{change_id}:{code}".encode(), hashlib.sha256).hexdigest()


def message(shop: str, provider: str, account: str, code: str) -> str:
    return (
        f"Fidelia : {shop} : demande de changement du portefeuille de paiement vers {provider.upper()} {mask(account)}.\n\n"
        f"Votre code de confirmation : *{code}*\n\n"
        "Saisissez-le dans Fidelia Pro pour confirmer. Si vous n'avez pas fait cette demande, touchez "
        "« Ce n'etait pas moi » dans l'application : rien ne sera change."
    )


async def event(db: AsyncSession, change: models.WalletChange, actor: str, action: str, detail: str | None = None) -> None:
    db.add(models.WalletChangeEvent(change_id=change.id, at=_now(), actor=actor, action=action, detail=(detail or None) and detail[:255]))


async def open_change(db: AsyncSession, venue_id: int) -> models.WalletChange | None:
    return (
        await db.execute(
            select(models.WalletChange).where(models.WalletChange.venue_id == venue_id, models.WalletChange.status.in_(OPEN_STATES)).order_by(models.WalletChange.id.desc())
        )
    ).scalars().first()


async def apply_due(db: AsyncSession, venue: models.Venue) -> None:
    """Activates a confirmed change whose delay is over. Called wherever the wallet is used or shown, so it needs no scheduler."""
    change = (
        await db.execute(select(models.WalletChange).where(models.WalletChange.venue_id == venue.id, models.WalletChange.status == "confirmed_waiting"))
    ).scalars().first()
    if change is not None and change.activates_at is not None and change.activates_at <= _now():
        await activate(db, venue, change, mode="auto", by="system")
        await db.commit()


async def activate(db: AsyncSession, venue: models.Venue, change: models.WalletChange, *, mode: str, by: str, note: str | None = None) -> None:
    from ..api.customer import new_pay_code  # local import: customer.py imports this module for the cap

    now = _now()
    venue.payout_provider, venue.payout_account = change.provider, change.account
    venue.wallet_active_since = now
    if not venue.pay_code:
        venue.pay_code = new_pay_code()  # a shop without a wallet had no payment QR: it gets one with its first wallet
    change.status, change.activated_at, change.activated_by, change.activation_mode, change.call_note = "active", now, by, mode, note
    await event(db, change, by, f"activated_{mode}", note)


async def request_change(db: AsyncSession, venue: models.Venue, provider: str, account: str, by: str) -> models.WalletChange:
    if open_ := await open_change(db, venue.id):
        raise HTTPException(status_code=409, detail="frozen_review" if open_.status == "frozen" else "change_in_progress")
    if venue.payout_provider == provider and venue.payout_account == account:
        raise HTTPException(status_code=409, detail="same_wallet")
    since = _now() - timedelta(days=1)
    recent = await db.scalar(select(func.count()).select_from(models.WalletChange).where(models.WalletChange.venue_id == venue.id, models.WalletChange.requested_at >= since))
    if (recent or 0) >= 3:
        raise HTTPException(status_code=429, detail="too_many_requests")
    change = models.WalletChange(
        venue_id=venue.id, provider=provider, account=account, prev_provider=venue.payout_provider, prev_account=venue.payout_account,
        status="pending_confirmation", requested_by=by, requested_at=_now(),
    )
    db.add(change)
    await db.flush()
    await event(db, change, by, "requested", f"{provider} {mask(account)}")
    return change


async def issue_code(db: AsyncSession, change: models.WalletChange, admin_key: str) -> str:
    """New code (the previous one stops working). Returned once, inside the wa.me link the admin sends from their own WhatsApp."""
    if change.status not in ("pending_confirmation", "confirmed_waiting"):
        raise HTTPException(status_code=409, detail="change_closed")
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    change.code_hash, change.code_expires_at, change.code_attempts = _hash(change.id, code), _now() + CODE_TTL, 0
    change.code_sent_by, change.code_sent_at = admin_key, _now()
    await event(db, change, admin_key, "code_sent")
    return code


async def confirm(db: AsyncSession, venue: models.Venue, change: models.WalletChange, code: str, by: str) -> None:
    if change.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="not_awaiting_code")
    now = _now()
    if change.code_hash is None or change.code_expires_at is None or change.code_expires_at <= now:
        raise HTTPException(status_code=400, detail="no_code")
    if change.code_attempts >= MAX_CODE_ATTEMPTS:
        raise HTTPException(status_code=429, detail="code_locked")
    change.code_attempts += 1
    if not hmac.compare_digest(change.code_hash, _hash(change.id, code)):
        await db.commit()  # the failed guess counts
        raise HTTPException(status_code=400, detail="wrong_code")
    change.code_hash = None
    change.confirmed_at = now
    first = not (venue.payout_provider and venue.payout_account)
    if first:
        await event(db, change, by, "confirmed", "first wallet: no delay")
        await activate(db, venue, change, mode="first_wallet", by=by)
        return
    change.status, change.activates_at = "confirmed_waiting", now + delay()
    await event(db, change, by, "confirmed", f"activates {change.activates_at.isoformat(timespec='minutes')}")


async def not_me(db: AsyncSession, change: models.WalletChange, by: str) -> None:
    if change.status not in ("pending_confirmation", "confirmed_waiting"):
        raise HTTPException(status_code=409, detail="change_closed")
    change.status, change.frozen_at = "frozen", _now()
    change.code_hash = None
    await event(db, change, by, "frozen_not_me")
    shop = change.venue.name if change.venue is not None else f"#{change.venue_id}"
    await admin_alerts.send("Portefeuille : « ce n'etait pas moi »", f"{shop} : changement gele, a verifier par telephone.", priority=5, tags=["warning", "rotating_light"])


async def reject(db: AsyncSession, change: models.WalletChange, admin_key: str, reason: str | None) -> None:
    if change.status not in OPEN_STATES:
        raise HTTPException(status_code=409, detail="change_closed")
    change.status, change.resolved_by, change.resolved_reason, change.code_hash = "rejected", admin_key, (reason or None) and reason[:255], None
    await event(db, change, admin_key, "rejected", reason)


async def cancel(db: AsyncSession, change: models.WalletChange, by: str) -> None:
    if change.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="cannot_cancel")
    change.status, change.resolved_by = "cancelled", by
    change.code_hash = None
    await event(db, change, by, "cancelled")


async def admin_activate_now(db: AsyncSession, venue: models.Venue, change: models.WalletChange, admin_key: str, call_note: str) -> None:
    """The admin phoned the merchant and checked who he is: the new wallet starts now, skipping the code and the delay. A frozen
    change ("this wasn't me") can NOT be activated this way: it must be rejected or re-requested."""
    if change.status not in ("pending_confirmation", "confirmed_waiting"):
        raise HTTPException(status_code=409, detail="frozen_review" if change.status == "frozen" else "change_closed")
    note = call_note.strip()
    if len(note) < 10:
        raise HTTPException(status_code=422, detail="call_note_required")
    await activate(db, venue, change, mode="admin_call", by=admin_key, note=note)
    day = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    today = await db.scalar(
        select(func.count()).select_from(models.WalletChange).where(
            models.WalletChange.activation_mode == "admin_call", models.WalletChange.activated_by == admin_key, models.WalletChange.activated_at >= day
        )
    )
    if (today or 0) >= fast_path_alert_threshold():
        await admin_alerts.send(
            "Portefeuilles actives par appel", f"Un admin a active {today} changements de portefeuille par appel aujourd'hui : a verifier.", priority=4, tags=["warning"]
        )


async def enforce_cap(db: AsyncSession, venue: models.Venue, amount: int) -> None:
    """First week of a newly activated wallet: at most `cap_xof()` received in total (payments in progress count)."""
    since = venue.wallet_active_since
    if since is None or _now() >= since + cap_window():
        return
    total = await db.scalar(
        select(func.coalesce(func.sum(models.CustomerPayment.amount), 0)).where(
            models.CustomerPayment.venue_id == venue.id, models.CustomerPayment.created_at >= since, models.CustomerPayment.status.in_(("pending", "succeeded"))
        )
    )
    if int(total or 0) + int(amount) > cap_xof():
        raise HTTPException(status_code=409, detail="wallet_cap_reached")
