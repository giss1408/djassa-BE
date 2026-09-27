from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.countries import get_country
from ..core.i18n import message
from ..core.security import get_current_user
from ..db import get_db
from ..models import SupportRequest
from ..schemas.support import SupportRequestIn, SupportRequestOut

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/requests", response_model=SupportRequestOut, status_code=201)
async def create_support_request(
    payload: SupportRequestIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    profile = get_country(payload.country_code)
    if profile is None:
        raise HTTPException(status_code=422, detail="Country is not supported")
    language = payload.language.lower()
    channel = payload.channel.lower()
    if language not in profile.languages:
        raise HTTPException(status_code=422, detail="Language is not supported for this country")
    if channel not in profile.support_channels:
        raise HTTPException(status_code=422, detail="Support channel is not available for this country")

    request = SupportRequest(
        user_id=user["username"],
        country_code=profile.code,
        language=language,
        channel=channel,
        category=payload.category.lower(),
        message=payload.message,
        status="open",
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return SupportRequestOut(
        id=request.id,
        status=request.status,
        country_code=request.country_code,
        language=request.language,
        channel=request.channel,
        category=request.category,
        message=request.message,
        confirmation=message("support_received", language),
        created_at=request.created_at,
    )
