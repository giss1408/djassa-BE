from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from fastapi.responses import StreamingResponse
import csv
import io

from ..db import get_db
from ..core.security import get_current_user
from .. import models
from ..schemas.tontine import (
    TontineGroupCreate,
    TontineGroupOut,
    JoinRequest,
    ContributionCreate,
    CycleOut,
)

router = APIRouter()


@router.post("/tontines", response_model=TontineGroupOut)
async def create_tontine(group_in: TontineGroupCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    user_id = user.get("username")
    group = models.TontineGroup(
        name=group_in.name,
        organizer_id=user_id,
        contribution_amount=group_in.contribution_amount,
        currency=group_in.currency or "XOF",
        frequency=group_in.frequency or "monthly",
        max_members=group_in.max_members,
        description=group_in.description,
    )
    db.add(group)
    await db.flush()
    db.add(models.TontineMember(group_id=group.id, user_id=user_id, is_admin=True))
    await db.commit()
    await db.refresh(group)
    return group


@router.post("/tontines/{group_id}/join")
async def join_tontine(group_id: int, req: JoinRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    # check group exists
    result = await db.execute(select(models.TontineGroup).where(models.TontineGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    user_id = user.get("username")
    # prevent duplicate
    res = await db.execute(select(models.TontineMember).where(models.TontineMember.group_id == group_id, models.TontineMember.user_id == user_id))
    existing = res.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already a member")
    member = models.TontineMember(group_id=group_id, user_id=user_id)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return {"member_id": member.id}


@router.post("/tontines/{group_id}/leave")
async def leave_tontine(group_id: int, req: JoinRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    user_id = user.get("username")
    res = await db.execute(select(models.TontineMember).where(models.TontineMember.group_id == group_id, models.TontineMember.user_id == user_id))
    member = res.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    member.active = False
    db.add(member)
    await db.commit()
    return {"left": True}


@router.post("/tontines/{group_id}/contribute")
async def contribute(group_id: int, contrib: ContributionCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    user_id = user.get("username")
    # find member
    res = await db.execute(select(models.TontineMember).where(models.TontineMember.group_id == group_id, models.TontineMember.user_id == user_id, models.TontineMember.active.is_(True)))
    member = res.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    grp_res = await db.execute(select(models.TontineGroup).where(models.TontineGroup.id == group_id))
    group = grp_res.scalar_one_or_none()
    currency = contrib.currency or (group.currency if group and getattr(group, 'currency', None) else "XOF")
    contribution = models.Contribution(
        group_id=group_id,
        member_id=member.id,
        amount=contrib.amount,
        currency=currency,
        payment_reference=contrib.payment_reference,
    )
    db.add(contribution)
    await db.commit()
    await db.refresh(contribution)
    return {"contribution_id": contribution.id}


@router.get("/tontines/{group_id}/cycles", response_model=List[CycleOut])
async def list_cycles(group_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    user_id = user.get("username")
    membership = await db.execute(select(models.TontineMember.id).where(models.TontineMember.group_id == group_id, models.TontineMember.user_id == user_id, models.TontineMember.active.is_(True)))
    if membership.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Group membership required")
    res = await db.execute(select(models.TontineCycle).where(models.TontineCycle.group_id == group_id))
    cycles = res.scalars().all()
    return cycles


@router.get("/tontines/{group_id}/export")
async def export_proof(group_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    user_id = user.get("username")
    membership = await db.execute(select(models.TontineMember.id).where(models.TontineMember.group_id == group_id, models.TontineMember.user_id == user_id, models.TontineMember.active.is_(True)))
    if membership.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Group membership required")
    # Export contributions for group as CSV
    # Members are loaded up front: the CSV is written where an async session
    # cannot lazy-load `c.member` (MissingGreenlet).
    query = select(models.Contribution).options(joinedload(models.Contribution.member)).where(models.Contribution.group_id == group_id)

    async def iter_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["member_id", "user_id", "amount", "currency", "paid_at", "payment_reference", "status"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        result = await db.stream_scalars(query)
        async for c in result:
            # fetch member to get user_id
            user_id = None
            if c.member:
                user_id = c.member.user_id
            writer.writerow([c.member_id, user_id, str(c.amount), c.currency, c.paid_at.isoformat() if c.paid_at else "", c.payment_reference or "", c.status])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(iter_csv(), media_type="text/csv")
