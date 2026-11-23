"""Wallet change process (see app/services/wallet_change.py for the whole story).

Merchant (Fidelia Pro):
    GET  /api/merchant/wallet                        the active wallet (masked) and the open change, if any
    POST /api/merchant/wallet-change                 {provider, account}  ask for a change (password re-entry at auth)
    POST /api/merchant/wallet-change/confirm         {code}               the code an admin sent on WhatsApp
    POST /api/merchant/wallet-change/not-me                               freeze it
    POST /api/merchant/wallet-change/cancel
Admins (authenticator code required, so only auth sign-ins):
    GET  /api/admin/wallet-changes?status=open|all
    POST /api/admin/wallet-changes/{id}/send-code     -> {"url": wa.me link}  the admin sends it from their own WhatsApp
    POST /api/admin/wallet-changes/{id}/activate-now  {call_note}             after a phone call with the merchant
    POST /api/admin/wallet-changes/{id}/reject        {reason}
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.phone import mask_phone
from ..core.security import require_role, require_step_up
from ..db import get_db
from ..services import wallet_change as svc
from .auth import phone_or_422
from .payment_requests import _my_venue

router = APIRouter()

Provider = Literal["wave", "orange", "mtn", "moov"]


async def sso_only(user=Depends(require_role("merchant"))):
    """The password re-entry (merchants) and the authenticator code (admins) live at the auth service: legacy sessions cannot do it."""
    if not user.get("sso"):
        raise HTTPException(status_code=403, detail="auth_login_required")
    return user


async def admin_sso_only(user=Depends(require_role("admin"))):
    if not user.get("sso"):
        raise HTTPException(status_code=403, detail="auth_login_required")
    return user


class RequestIn(BaseModel):
    provider: Provider
    account: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


class CodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class CallIn(BaseModel):
    call_note: str = Field(min_length=1, max_length=500)


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class ChangeOut(BaseModel):
    id: int
    status: str
    provider: str
    account_masked: str
    requested_at: datetime
    code_sent: bool
    confirmed_at: datetime | None
    activates_at: datetime | None
    activated_at: datetime | None
    activation_mode: str | None


class WalletOut(BaseModel):
    provider: str | None
    account_masked: str | None
    active_since: datetime | None
    cap_xof: int | None  # set during the first week of a new wallet
    change: ChangeOut | None


def _change_out(c: models.WalletChange) -> ChangeOut:
    return ChangeOut(id=c.id, status=c.status, provider=c.provider, account_masked=svc.mask(c.account) or "", requested_at=c.requested_at, code_sent=c.code_sent_at is not None,
                     confirmed_at=c.confirmed_at, activates_at=c.activates_at, activated_at=c.activated_at, activation_mode=c.activation_mode)


async def _state(db: AsyncSession, venue: models.Venue) -> WalletOut:
    await svc.apply_due(db, venue)
    await db.refresh(venue)
    change = await svc.open_change(db, venue.id)
    if change is None:
        change = (await db.execute(select(models.WalletChange).where(models.WalletChange.venue_id == venue.id).order_by(models.WalletChange.id.desc()))).scalars().first()
    in_window = venue.wallet_active_since is not None and svc._now() < venue.wallet_active_since + svc.cap_window()
    return WalletOut(provider=venue.payout_provider, account_masked=svc.mask(venue.payout_account), active_since=venue.wallet_active_since,
                     cap_xof=svc.cap_xof() if in_window else None, change=_change_out(change) if change else None)


@router.get("/merchant/wallet", response_model=WalletOut)
async def my_wallet(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    return await _state(db, await _my_venue(db, user, require_wallet=False))


@router.post("/merchant/wallet-change", response_model=ChangeOut, status_code=201, dependencies=[Depends(require_step_up())])
async def request_wallet_change(payload: RequestIn, db: AsyncSession = Depends(get_db), user=Depends(sso_only)):
    venue = await _my_venue(db, user, require_wallet=False)
    account = phone_or_422(payload.account, payload.country_code)
    change = await svc.request_change(db, venue, payload.provider, account, user["username"])
    await db.commit()
    return _change_out(change)


async def _my_open(db: AsyncSession, venue: models.Venue) -> models.WalletChange:
    change = await svc.open_change(db, venue.id)
    if change is None:
        raise HTTPException(status_code=404, detail="no_open_change")
    return change


@router.post("/merchant/wallet-change/confirm", response_model=ChangeOut)
async def confirm_wallet_change(payload: CodeIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    change = await _my_open(db, venue)
    await svc.confirm(db, venue, change, payload.code, user["username"])
    await db.commit()
    return _change_out(change)


@router.post("/merchant/wallet-change/not-me", response_model=ChangeOut)
async def wallet_change_not_me(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    """Any merchant session may press it, including a legacy one: it only ever makes things safer."""
    venue = await _my_venue(db, user, require_wallet=False)
    change = await _my_open(db, venue)
    change.venue = venue
    await svc.not_me(db, change, user["username"])
    await db.commit()
    return _change_out(change)


@router.post("/merchant/wallet-change/cancel", response_model=ChangeOut)
async def cancel_wallet_change(db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    change = await _my_open(db, venue)
    await svc.cancel(db, change, user["username"])
    await db.commit()
    return _change_out(change)


# ---- admins ----


class AdminChangeOut(ChangeOut):
    shop: str
    venue_id: int
    merchant_phone_masked: str | None
    current_account_masked: str | None
    call_note: str | None
    events: list[dict]


async def _load(db: AsyncSession, change_id: int) -> tuple[models.WalletChange, models.Venue]:
    change = await db.get(models.WalletChange, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="change_not_found")
    venue = await db.get(models.Venue, change.venue_id)
    return change, venue


@router.get("/admin/wallet-changes", response_model=list[AdminChangeOut], dependencies=[Depends(require_step_up())])
async def list_wallet_changes(status: Literal["open", "all"] = "open", db: AsyncSession = Depends(get_db), admin=Depends(admin_sso_only)):
    q = select(models.WalletChange).order_by(models.WalletChange.id.desc()).limit(200)
    if status == "open":
        q = q.where(models.WalletChange.status.in_(svc.OPEN_STATES))
    out = []
    for c in (await db.execute(q)).scalars().all():
        v = await db.get(models.Venue, c.venue_id)
        events = (await db.execute(select(models.WalletChangeEvent).where(models.WalletChangeEvent.change_id == c.id).order_by(models.WalletChangeEvent.id))).scalars().all()
        owner = v.owner_username or ""
        out.append(AdminChangeOut(**_change_out(c).model_dump(), shop=v.name, venue_id=v.id, merchant_phone_masked=mask_phone(owner[4:]) if owner.startswith("tel:") else None,
                                  current_account_masked=svc.mask(c.prev_account), call_note=c.call_note,
                                  events=[{"at": e.at.isoformat(), "actor_masked": mask_phone(e.actor[4:]) if e.actor.startswith("tel:") else e.actor, "action": e.action, "detail": e.detail} for e in events]))
    return out


@router.post("/admin/wallet-changes/{change_id}/send-code", dependencies=[Depends(require_step_up())])
async def send_wallet_code(change_id: int, db: AsyncSession = Depends(get_db), admin=Depends(admin_sso_only)):
    """New code + wa.me link to the merchant's LOGIN number: the admin sends it from their WhatsApp, the merchant types it in the app."""
    change, venue = await _load(db, change_id)
    owner = venue.owner_username or ""
    if not owner.startswith("tel:"):
        raise HTTPException(status_code=409, detail="shop_has_no_merchant")
    code = await svc.issue_code(db, change, admin["username"])
    await db.commit()
    return {"url": svc.wa_link(owner[4:], svc.message(venue.name, change.provider, change.account, code))}


@router.post("/admin/wallet-changes/{change_id}/activate-now", response_model=ChangeOut, dependencies=[Depends(require_step_up())])
async def activate_wallet_now(change_id: int, payload: CallIn, db: AsyncSession = Depends(get_db), admin=Depends(admin_sso_only)):
    change, venue = await _load(db, change_id)
    await svc.admin_activate_now(db, venue, change, admin["username"], payload.call_note)
    await db.commit()
    return _change_out(change)


@router.post("/admin/wallet-changes/{change_id}/reject", response_model=ChangeOut, dependencies=[Depends(require_step_up())])
async def reject_wallet_change(change_id: int, payload: RejectIn, db: AsyncSession = Depends(get_db), admin=Depends(admin_sso_only)):
    change, _venue = await _load(db, change_id)
    await svc.reject(db, change, admin["username"], payload.reason)
    await db.commit()
    return _change_out(change)
