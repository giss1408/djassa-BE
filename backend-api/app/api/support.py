import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.countries import get_country
from ..core.i18n import message
from ..core.security import SHOP_STAFF, get_current_user
from ..db import get_db
from ..models import LoyaltyEntry, SupportRequest
from ..schemas.support import SupportRequestIn, SupportRequestOut

router = APIRouter(prefix="/support", tags=["support"])

# Customers unlock "send a suggestion on WhatsApp" at this many points: a
# regular, not a stranger, so the team's WhatsApp is not a spam inbox. The
# points are a threshold, never spent. Merchants and their cashiers always
# have it, free: they are who Hossouko is built for.
SUGGESTION_POINTS = 100


def suggestions_whatsapp() -> str | None:
    """The Hossouko team's WhatsApp number, digits only (wa.me format)."""
    digits = "".join(c for c in os.getenv("HOSSOUKO_SUGGESTIONS_WHATSAPP", "") if c.isdigit())
    return digits or None


class SuggestionAccessOut(BaseModel):
    available: bool
    # None until the number is configured, or while the customer is short.
    whatsapp_url: str | None = None
    points: int | None = None  # customers only: their total across venues
    points_needed: int = SUGGESTION_POINTS


@router.get("/suggestions/whatsapp", response_model=SuggestionAccessOut)
async def suggestion_access(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Whether this person may message the team on WhatsApp, and the link.

    The apps keep the menu entry out of sight until `available` is true."""
    number = suggestions_whatsapp()
    staff = user["role"] in SHOP_STAFF
    points = None
    if not staff:
        points = int(
            (
                await db.execute(
                    select(func.coalesce(func.sum(LoyaltyEntry.points), 0)).where(
                        LoyaltyEntry.customer_id == user["username"]
                    )
                )
            ).scalar_one()
        )
    allowed = staff or (points or 0) >= SUGGESTION_POINTS
    if not allowed or number is None:
        return SuggestionAccessOut(available=False, points=points)
    who = "commercant" if staff else "client"
    text = f"Suggestion Hossouko ({who}) : "
    return SuggestionAccessOut(available=True, whatsapp_url=f"https://wa.me/{number}?text={quote(text)}", points=points)


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
