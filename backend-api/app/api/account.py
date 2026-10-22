"""Account recovery, for an account that is a phone number.

Three situations, three paths:

* **Phone lost or stolen, number kept** (a replacement SIM): sign in again
  with the password, then end every other session.
      POST /api/auth/sessions/revoke-others
* **New number, old SIM still at hand**: the password again, then a code the
  team sends on WhatsApp to the new number, and the account moves at once.
      POST /api/auth/change-number/request   (signed in) password + new number
      POST /api/auth/change-number/confirm   (signed in) the code
* **Old number gone**: register the new number (the team checks it on
  WhatsApp), describe the account, and a person decides.
      POST /api/auth/recovery                (signed in on the new number)
      GET  /api/admin/recovery-requests      what an admin needs to check it
      POST /api/admin/recovery-requests/{id}/approve | /reject

A move re-keys everything the person owns (`app/services/account_move.py`)
and revokes every session, so whoever holds the old number, or a phone signed
in on it, is out.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core import otp, passwords, security
from ..core.phone import mask_phone, phone_key
from ..db import get_db
from ..rate_limiter import limiter
from ..services import account_checks, account_delete
from ..services.account_move import (
    NumberTaken, move_account, owns_nothing, revoke_all_sessions, revoke_role_sessions,
)
from .auth import TokenPairOut, issue_tokens, phone_or_422, utcnow

router = APIRouter()

_NUMBER_TAKEN = "Ce numero a deja un compte Fidelia. Contactez Fidelia pour regrouper les deux."


async def _phone_account(db: AsyncSession, user) -> models.User:
    """The User behind a phone-login token. Demo accounts have none."""
    sub = user["username"]
    account = None
    if sub.startswith("tel:"):
        account = (await db.execute(select(models.User).where(models.User.phone_e164 == sub[4:]))).scalar_one_or_none()
    if account is None or account.disabled:
        raise HTTPException(status_code=403, detail="Disponible uniquement pour un compte connecte par telephone")
    return account


# --- Sign out everywhere else ------------------------------------------------


class RevokeOthersIn(BaseModel):
    # This device's refresh token, so it stays signed in. Optional: without it
    # every session ends, this one included once its access token expires.
    refresh_token: str | None = Field(default=None, min_length=20, max_length=128)


@router.post("/auth/sessions/revoke-others")
async def revoke_other_sessions(payload: RevokeOthersIn, db: AsyncSession = Depends(get_db), user=Depends(security.get_current_user)):
    """Ends every other session. Their access tokens die within the hour."""
    account = await _phone_account(db, user)
    keep = otp.hash_refresh_token(payload.refresh_token) if payload.refresh_token else None
    revoked = await revoke_all_sessions(db, account.id, utcnow(), keep_token_hash=keep)
    await db.commit()
    return {"revoked": revoked}


# --- Change number, old SIM in hand -------------------------------------------


class ChangeNumberRequestIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    new_phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


class ChangeNumberRequestOut(BaseModel):
    new_phone_masked: str


class ChangeNumberConfirmIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


async def _new_number(db: AsyncSession, account: models.User, raw: str, country_code: str) -> str:
    e164 = phone_or_422(raw, country_code)
    if e164 == account.phone_e164:
        raise HTTPException(status_code=422, detail="C'est deja le numero de ce compte")
    if (await db.execute(select(models.User.id).where(models.User.phone_e164 == e164))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=_NUMBER_TAKEN)
    return e164


@router.post("/auth/change-number/request", response_model=ChangeNumberRequestOut, status_code=202)
@limiter.limit("5/minute")
async def request_number_change(
    request: Request, payload: ChangeNumberRequestIn, db: AsyncSession = Depends(get_db), user=Depends(security.get_current_user)
):
    """Asks the team for a code on the new number. The password proves the
    person, not just a session: a phone left unlocked must not be enough to
    take the account away."""
    account = await _phone_account(db, user)
    if not account.password_hash or not passwords.verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")
    new_e164 = await _new_number(db, account, payload.new_phone, payload.country_code)
    await account_checks.open_check(db, account, "change_number", utcnow(), new_phone_e164=new_e164)
    await db.commit()
    return ChangeNumberRequestOut(new_phone_masked=mask_phone(new_e164))


@router.post("/auth/change-number/confirm", response_model=TokenPairOut)
@limiter.limit("10/minute")
async def confirm_number_change(
    request: Request, payload: ChangeNumberConfirmIn, db: AsyncSession = Depends(get_db), user=Depends(security.get_current_user)
):
    """Moves the account and returns a fresh session on the new number. Every
    other session, on any device, ends."""
    account = await _phone_account(db, user)
    now = utcnow()
    try:
        check = await account_checks.verify_code(db, account, "change_number", payload.code.replace(" ", ""), now)
    except account_checks.BadCode:
        raise HTTPException(status_code=401, detail="Code incorrect ou expire.")
    if not check.new_phone_e164:
        raise HTTPException(status_code=401, detail="Code incorrect ou expire.")
    try:
        await move_account(db, account, check.new_phone_e164, method="self_service", now=now)
    except NumberTaken:
        raise HTTPException(status_code=409, detail=_NUMBER_TAKEN)
    pair = await issue_tokens(db, account, user["role"], otp.new_family(), now)
    await db.commit()
    return pair


# --- Lost number: reviewed by a person ---------------------------------------


class RecoveryIn(BaseModel):
    old_phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    details: str = Field(min_length=10, max_length=1000)


@router.post("/auth/recovery", status_code=202)
@limiter.limit("5/minute;20/hour")
async def file_recovery(
    request: Request, payload: RecoveryIn, db: AsyncSession = Depends(get_db), user=Depends(security.get_current_user)
):
    """Files the request from a session on the new number, which the team has
    already checked on WhatsApp. The answer is the same whether or not the old
    number has an account, so this cannot be used to find out who uses
    Fidelia."""
    account = await _phone_account(db, user)
    new_e164 = account.phone_e164
    old_e164 = phone_or_422(payload.old_phone, payload.country_code)
    if old_e164 == new_e164:
        raise HTTPException(status_code=422, detail="Le nouveau numero doit etre different de l'ancien")
    now = utcnow()
    pending = (
        await db.execute(
            select(models.RecoveryRequest.id).where(
                models.RecoveryRequest.new_phone_e164 == new_e164, models.RecoveryRequest.status == "pending"
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise HTTPException(status_code=409, detail="Une demande est deja en cours pour ce numero. Nous vous contacterons.")

    db.add(
        models.RecoveryRequest(
            old_phone_e164=old_e164, new_phone_e164=new_e164, details=payload.details.strip(),
            status="pending", created_at=now,
        )
    )
    await db.commit()
    return {
        "status": "pending",
        "message": "Demande recue. Fidelia vous contactera pour verifier. "
        "Une fois validee, connectez-vous avec ce numero.",
    }


class RecoveryAccountOut(BaseModel):
    roles: list[str]
    created_at: datetime
    last_login_at: datetime | None
    venues_owned: list[str]
    loyalty_venues: list[str]
    last_payment_at: datetime | None


class RecoveryRequestOut(BaseModel):
    id: int
    old_phone: str
    new_phone: str
    details: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decision_note: str | None
    # None when the old number has no account: nothing to recover.
    old_account: RecoveryAccountOut | None
    # Requests for the same old number. More than one is a reason to call.
    requests_for_old_number: int


async def _account_summary(db: AsyncSession, e164: str) -> RecoveryAccountOut | None:
    """What an admin can ask the caller about to check the claim."""
    account = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if account is None:
        return None
    key = phone_key(e164)
    owned = (await db.execute(select(models.Venue.name).where(models.Venue.owner_username == key))).scalars().all()
    loyalty = (
        await db.execute(
            select(models.Venue.name)
            .join(models.LoyaltyEntry, models.LoyaltyEntry.venue_id == models.Venue.id)
            .where(models.LoyaltyEntry.customer_id == key)
            .distinct()
            .limit(5)
        )
    ).scalars().all()
    last_payment = (
        await db.execute(select(func.max(models.CustomerPayment.created_at)).where(models.CustomerPayment.customer_id == key))
    ).scalar_one_or_none()
    return RecoveryAccountOut(
        roles=sorted(account.role_set()), created_at=account.created_at, last_login_at=account.last_login_at,
        venues_owned=list(owned), loyalty_venues=list(loyalty), last_payment_at=last_payment,
    )


async def _out(db: AsyncSession, r: models.RecoveryRequest) -> RecoveryRequestOut:
    count = (
        await db.execute(select(func.count(models.RecoveryRequest.id)).where(models.RecoveryRequest.old_phone_e164 == r.old_phone_e164))
    ).scalar_one()
    return RecoveryRequestOut(
        id=r.id, old_phone=r.old_phone_e164, new_phone=r.new_phone_e164, details=r.details, status=r.status,
        created_at=r.created_at, decided_at=r.decided_at, decided_by=r.decided_by, decision_note=r.decision_note,
        old_account=await _account_summary(db, r.old_phone_e164), requests_for_old_number=count,
    )


@router.get("/admin/recovery-requests", response_model=list[RecoveryRequestOut])
async def list_recovery_requests(
    status: str = "pending", db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    rows = (
        await db.execute(
            select(models.RecoveryRequest)
            .where(models.RecoveryRequest.status == status)
            .order_by(models.RecoveryRequest.created_at)
            .limit(100)
        )
    ).scalars().all()
    return [await _out(db, r) for r in rows]


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


async def _pending(db: AsyncSession, request_id: int) -> models.RecoveryRequest:
    r = await db.get(models.RecoveryRequest, request_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Recovery request not found")
    if r.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {r.status}")
    return r


async def _drop_placeholder(db: AsyncSession, placeholder: models.User, keeper: models.User) -> None:
    """Deletes the bare account on the new number. Its history rows (admin
    actions, number changes) now belong to the account that takes the number."""
    await db.execute(update(models.AdminAction).where(models.AdminAction.user_id == placeholder.id).values(user_id=keeper.id))
    await db.execute(update(models.AccountNumberChange).where(models.AccountNumberChange.user_id == placeholder.id).values(user_id=keeper.id))
    await db.execute(delete(models.RefreshToken).where(models.RefreshToken.user_id == placeholder.id))
    await db.execute(delete(models.AccountCheck).where(models.AccountCheck.user_id == placeholder.id))
    await db.delete(placeholder)
    await db.flush()


@router.post("/admin/recovery-requests/{request_id}/approve", response_model=RecoveryRequestOut)
async def approve_recovery(
    request_id: int, payload: DecisionIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    r = await _pending(db, request_id)
    account = (await db.execute(select(models.User).where(models.User.phone_e164 == r.old_phone_e164))).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=409, detail="The old number has no account; reject the request")
    now = utcnow()
    # The person registered the new number first, so it holds a bare customer
    # account. That placeholder gives way (its password and proven number come
    # along); anything more is two accounts to regroup by hand.
    placeholder = (await db.execute(select(models.User).where(models.User.phone_e164 == r.new_phone_e164))).scalar_one_or_none()
    if placeholder is not None:
        if placeholder.role_set() != {"customer"} or not await owns_nothing(db, phone_key(r.new_phone_e164)):
            raise HTTPException(status_code=409, detail="The new number already has an account")
        account.password_hash = placeholder.password_hash
        account.phone_verified_at = placeholder.phone_verified_at
        await _drop_placeholder(db, placeholder, account)
    try:
        await move_account(db, account, r.new_phone_e164, method="recovery", now=now, recovery_request_id=r.id)
    except NumberTaken:
        raise HTTPException(status_code=409, detail="The new number already has an account")
    r.status, r.decided_at, r.decided_by, r.decision_note = "approved", now, admin["username"], payload.note
    await db.commit()
    return await _out(db, r)


@router.post("/admin/recovery-requests/{request_id}/reject", response_model=RecoveryRequestOut)
async def reject_recovery(
    request_id: int, payload: DecisionIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    r = await _pending(db, request_id)
    r.status, r.decided_at, r.decided_by, r.decision_note = "rejected", utcnow(), admin["username"], payload.note
    await db.commit()
    return await _out(db, r)


class RevokeSessionsIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


@router.post("/admin/users/revoke-sessions")
async def admin_revoke_sessions(payload: RevokeSessionsIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))):
    """A reported theft: end every session of that number now."""
    e164 = phone_or_422(payload.phone, payload.country_code)
    account = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="No account for this number")
    revoked = await revoke_all_sessions(db, account.id, utcnow())
    await db.commit()
    return {"revoked": revoked}


# --- Users, for the admin screen ---------------------------------------------


class UserOut(BaseModel):
    phone: str
    roles: list[str]
    disabled: bool
    created_at: datetime
    last_login_at: datetime | None
    venues_owned: list[str]
    active_sessions: int


class PhoneIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    country_code: str = Field(default="CI", min_length=2, max_length=2)


class DisableIn(PhoneIn):
    disabled: bool


class RevokeRoleIn(PhoneIn):
    role: str = Field(pattern=r"^(merchant|agent|admin)$")


async def _user_out(db: AsyncSession, account: models.User) -> UserOut:
    key = phone_key(account.phone_e164)
    owned = (await db.execute(select(models.Venue.name).where(models.Venue.owner_username == key))).scalars().all()
    sessions = (
        await db.execute(
            select(func.count(models.RefreshToken.id)).where(
                models.RefreshToken.user_id == account.id,
                models.RefreshToken.revoked_at.is_(None),
                models.RefreshToken.rotated_at.is_(None),
                models.RefreshToken.expires_at > utcnow(),
            )
        )
    ).scalar_one()
    return UserOut(
        phone=account.phone_e164, roles=sorted(account.role_set()), disabled=account.disabled,
        created_at=account.created_at, last_login_at=account.last_login_at,
        venues_owned=list(owned), active_sessions=sessions,
    )


async def _user_by_phone(db: AsyncSession, raw: str, country_code: str) -> models.User:
    e164 = phone_or_422(raw, country_code)
    account = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="No account for this number")
    return account


@router.get("/admin/users", response_model=UserOut)
async def admin_find_user(phone: str, country_code: str = "CI", db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))):
    return await _user_out(db, await _user_by_phone(db, phone, country_code))


@router.post("/admin/users/disable", response_model=UserOut)
async def admin_disable_user(payload: DisableIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))):
    """Suspends (or restores) an account. Suspending also ends its sessions."""
    account = await _user_by_phone(db, payload.phone, payload.country_code)
    if payload.disabled and admin["username"] == phone_key(account.phone_e164):
        raise HTTPException(status_code=422, detail="You cannot suspend your own account")
    account.disabled = payload.disabled
    if payload.disabled:
        await revoke_all_sessions(db, account.id, utcnow())
    await db.commit()
    return await _user_out(db, account)


@router.post("/admin/users/roles/revoke", response_model=UserOut)
async def admin_revoke_role(payload: RevokeRoleIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))):
    """Removes merchant, field agent or admin access. Sessions for that role
    cannot renew; an access token already issued lives out its hour."""
    account = await _user_by_phone(db, payload.phone, payload.country_code)
    if payload.role == "admin" and admin["username"] == phone_key(account.phone_e164):
        raise HTTPException(status_code=422, detail="You cannot remove your own admin access")
    account.roles = ",".join(sorted(account.role_set() - {payload.role})) or "customer"
    await revoke_role_sessions(db, account.id, payload.role, utcnow())
    await db.commit()
    return await _user_out(db, account)


# --- Deleting an account (Google Play's account deletion requirement) --------

_DELETE_STAFF = (
    "Votre numero est lie a un commerce Fidelia. Demandez la suppression depuis Fidelia Pro : "
    "l'equipe Fidelia s'en occupe."
)
_DELETE_LAYAWAY = (
    "Un paiement en plusieurs fois est en cours. Terminez-le ou annulez-le avec le commercant, "
    "puis supprimez votre compte."
)


@router.delete("/account")
async def delete_my_account(db: AsyncSession = Depends(get_db), user=Depends(security.require_role("customer"))):
    """A customer deletes their own account, at once (services/account_delete.py)."""
    account = await _phone_account(db, user)
    try:
        await account_delete.delete_account(db, account, utcnow())
    except account_delete.IsShopStaff:
        raise HTTPException(status_code=409, detail=_DELETE_STAFF)
    except account_delete.LayawayInProgress:
        raise HTTPException(status_code=409, detail=_DELETE_LAYAWAY)
    await db.commit()
    return {"deleted": True}


class DeletionRequestIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class DeletionRequestOut(BaseModel):
    id: int
    phone: str
    role: str
    venue_id: int | None
    venue_name: str | None
    reason: str | None
    status: str
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


async def _deletion_out(db: AsyncSession, r: models.AccountDeletionRequest) -> DeletionRequestOut:
    venue = await db.get(models.Venue, r.venue_id) if r.venue_id else None
    return DeletionRequestOut(
        id=r.id, phone=r.phone_e164, role=r.role, venue_id=r.venue_id, venue_name=venue.name if venue else None,
        reason=r.reason, status=r.status, decision_note=r.decision_note, created_at=r.created_at, decided_at=r.decided_at,
    )


@router.post("/account/deletion-request", status_code=202)
async def request_account_deletion(
    payload: DeletionRequestIn, db: AsyncSession = Depends(get_db), user=Depends(security.get_current_user)
):
    """Merchants, cashiers and field agents ask; an admin closes or hands over
    the shop, then deletes. One pending request per number: asking again
    returns the same one."""
    account = await _phone_account(db, user)
    existing = (
        await db.execute(
            select(models.AccountDeletionRequest).where(
                models.AccountDeletionRequest.phone_e164 == account.phone_e164,
                models.AccountDeletionRequest.status == "pending",
            )
        )
    ).scalars().first()
    if existing is None:
        key = phone_key(account.phone_e164)
        venue = (await db.execute(select(models.Venue).where(models.Venue.owner_username == key))).scalars().first()
        if venue is None:
            venue = (
                await db.execute(
                    select(models.Venue)
                    .join(models.VenueStaff, models.VenueStaff.venue_id == models.Venue.id)
                    .where(models.VenueStaff.user_key == key, models.VenueStaff.removed_at.is_(None))
                )
            ).scalars().first()
        existing = models.AccountDeletionRequest(
            phone_e164=account.phone_e164, role=user["role"], venue_id=venue.id if venue else None,
            reason=payload.reason, status="pending", created_at=utcnow(),
        )
        db.add(existing)
        await db.commit()
    return {"id": existing.id, "status": existing.status,
            "message": "Demande recue. L'equipe Fidelia vous contacte et supprime votre compte sous 30 jours."}


@router.get("/admin/deletion-requests", response_model=list[DeletionRequestOut])
async def list_deletion_requests(
    status: str = "pending", db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    rows = (
        await db.execute(
            select(models.AccountDeletionRequest)
            .where(models.AccountDeletionRequest.status == status)
            .order_by(models.AccountDeletionRequest.created_at)
        )
    ).scalars().all()
    return [await _deletion_out(db, r) for r in rows]


async def _pending_deletion(db: AsyncSession, request_id: int) -> models.AccountDeletionRequest:
    r = await db.get(models.AccountDeletionRequest, request_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if r.status != "pending":
        raise HTTPException(status_code=409, detail="Demande deja traitee")
    return r


@router.post("/admin/deletion-requests/{request_id}/done", response_model=DeletionRequestOut)
async def complete_deletion_request(
    request_id: int, payload: DecisionIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    """Deletes the account. Refused while it still owns a shop: close the shop
    or give it another owner first. A cashier's place in the shop ends."""
    r = await _pending_deletion(db, request_id)
    if admin["username"] == phone_key(r.phone_e164):
        raise HTTPException(status_code=422, detail="You cannot delete your own account")
    account = (
        await db.execute(select(models.User).where(models.User.phone_e164 == r.phone_e164))
    ).scalar_one_or_none()
    now = utcnow()
    if account is not None:
        try:
            await account_delete.delete_account(db, account, now, staff=True, decided_by=admin["username"])
        except account_delete.OwnsShop:
            raise HTTPException(
                status_code=409, detail="Ce numero possede encore un commerce : fermez-le ou changez son proprietaire d'abord."
            )
        except account_delete.LayawayInProgress:
            raise HTTPException(status_code=409, detail=_DELETE_LAYAWAY)
    r.status, r.decision_note, r.decided_by, r.decided_at = "done", payload.note, admin["username"], now
    await db.commit()
    return await _deletion_out(db, r)


@router.post("/admin/deletion-requests/{request_id}/reject", response_model=DeletionRequestOut)
async def reject_deletion_request(
    request_id: int, payload: DecisionIn, db: AsyncSession = Depends(get_db), admin=Depends(security.require_role("admin"))
):
    r = await _pending_deletion(db, request_id)
    r.status, r.decision_note, r.decided_by, r.decided_at = "rejected", payload.note, admin["username"], utcnow()
    await db.commit()
    return await _deletion_out(db, r)
