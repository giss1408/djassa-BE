"""Routes the Fidelia Admin app calls: send or refuse the WhatsApp checks the
team handles by hand, and look after accounts. Every call, reads included,
leaves one `AdminAction` row."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core import security
from ..core.phone import mask_phone
from ..db import get_db
from ..services import account_checks
from ..services.account_move import revoke_all_sessions
from .auth import phone_or_422, utcnow

router = APIRouter()

_DONE = "Cette demande est deja traitee."


class CheckOut(BaseModel):
    id: int
    kind: str
    app: Literal["customer", "merchant"]
    phone_masked: str
    created_at: datetime
    sent_at: datetime | None
    team_created: bool


class UserOut(BaseModel):
    id: int
    phone_masked: str
    roles: list[str]
    disabled: bool
    verified: bool
    last_login_at: datetime | None


class UrlOut(BaseModel):
    url: str


class CheckIdOut(BaseModel):
    check_id: int


async def admin_user(db: AsyncSession = Depends(get_db), token_user=Depends(security.require_role("admin"))) -> models.User:
    """The admin's own User row, from the token subject."""
    sub = token_user["username"]
    admin = None
    if sub.startswith("tel:"):
        admin = (await db.execute(select(models.User).where(models.User.phone_e164 == sub[4:]))).scalar_one_or_none()
    if admin is None or admin.disabled:
        raise HTTPException(status_code=403, detail="Not allowed for this account")
    return admin


def _log(db: AsyncSession, request: Request, admin: models.User, action: str, user_id=None, check_id=None) -> None:
    db.add(
        models.AdminAction(
            admin_user_id=admin.id, action=action, user_id=user_id, check_id=check_id,
            ip=request.client.host if request.client else None, created_at=utcnow(),
        )
    )


def _app_of(user: models.User) -> str:
    return "merchant" if user.role_set() & {"merchant", "cashier"} else "customer"


async def _open_check(db: AsyncSession, check_id: int) -> tuple[models.AccountCheck, models.User]:
    check = await db.get(models.AccountCheck, check_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    if check.status not in account_checks.OPEN_STATUSES:
        raise HTTPException(status_code=409, detail=_DONE)
    return check, await db.get(models.User, check.user_id)


async def _user(db: AsyncSession, user_id: int) -> models.User:
    user = await db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Compte introuvable.")
    return user


@router.get("/checks", response_model=list[CheckOut])
async def list_checks(
    request: Request,
    kind: Literal["verify_number", "reset_password", "change_number"] | None = None,
    db: AsyncSession = Depends(get_db),
    admin: models.User = Depends(admin_user),
):
    query = (
        select(models.AccountCheck, models.User)
        .join(models.User, models.User.id == models.AccountCheck.user_id)
        .where(models.AccountCheck.status.in_(account_checks.OPEN_STATUSES))
        .order_by(models.AccountCheck.created_at, models.AccountCheck.id)
    )
    if kind:
        query = query.where(models.AccountCheck.kind == kind)
    rows = (await db.execute(query)).all()
    _log(db, request, admin, "list_checks")
    await db.commit()
    return [
        CheckOut(
            id=c.id, kind=c.kind, app=_app_of(u), phone_masked=mask_phone(u.phone_e164),
            created_at=c.created_at, sent_at=c.sent_at, team_created=bool(c.team_created),
        )
        for c, u in rows
    ]


@router.post("/checks/{check_id}/send", response_model=UrlOut)
async def send_check(check_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: models.User = Depends(admin_user)):
    check, user = await _open_check(db, check_id)
    if user.disabled:
        raise HTTPException(status_code=409, detail="Ce compte est suspendu.")
    url = await account_checks.send_check(db, check, admin.id, utcnow())
    _log(db, request, admin, "send_check", user_id=user.id, check_id=check.id)
    await db.commit()
    return UrlOut(url=url)


@router.post("/checks/{check_id}/refuse", status_code=204)
async def refuse_check(check_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: models.User = Depends(admin_user)):
    check, user = await _open_check(db, check_id)
    await account_checks.refuse(db, check, utcnow())
    _log(db, request, admin, "refuse_check", user_id=user.id, check_id=check.id)
    await db.commit()
    return Response(status_code=204)


@router.get("/users", response_model=UserOut)
async def find_user(
    request: Request, phone: str, country_code: str = "CI",
    db: AsyncSession = Depends(get_db), admin: models.User = Depends(admin_user),
):
    e164 = phone_or_422(phone, country_code)
    user = (await db.execute(select(models.User).where(models.User.phone_e164 == e164))).scalar_one_or_none()
    _log(db, request, admin, "find_user", user_id=user.id if user else None)
    await db.commit()
    if user is None:
        raise HTTPException(status_code=404, detail="Compte introuvable.")
    return UserOut(
        id=user.id, phone_masked=mask_phone(user.phone_e164), roles=sorted(user.role_set()),
        disabled=bool(user.disabled), verified=user.phone_verified_at is not None, last_login_at=user.last_login_at,
    )


@router.post("/users/{user_id}/suspend", status_code=204)
async def suspend(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: models.User = Depends(admin_user)):
    user = await _user(db, user_id)
    user.disabled = True
    await revoke_all_sessions(db, user.id, utcnow())
    _log(db, request, admin, "suspend", user_id=user.id)
    await db.commit()
    return Response(status_code=204)


@router.post("/users/{user_id}/restore", status_code=204)
async def restore(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: models.User = Depends(admin_user)):
    user = await _user(db, user_id)
    user.disabled = False
    _log(db, request, admin, "restore", user_id=user.id)
    await db.commit()
    return Response(status_code=204)


@router.post("/users/{user_id}/sign-out", status_code=204)
async def sign_out(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: models.User = Depends(admin_user)):
    user = await _user(db, user_id)
    await revoke_all_sessions(db, user.id, utcnow())
    _log(db, request, admin, "sign_out", user_id=user.id)
    await db.commit()
    return Response(status_code=204)


@router.post("/users/{user_id}/reset-password", response_model=CheckIdOut)
async def reset_password(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: models.User = Depends(admin_user)):
    """Opens the check; the user keeps the old password until they use the temporary one."""
    user = await _user(db, user_id)
    check = await account_checks.open_check(db, user, "reset_password", utcnow(), team_created=False)
    _log(db, request, admin, "reset_password", user_id=user.id, check_id=check.id)
    await db.commit()
    return CheckIdOut(check_id=check.id)
