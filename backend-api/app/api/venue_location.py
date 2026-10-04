"""The merchant sets their own shop's position, from the phone's GPS.

The merchant app asks "are you in your shop right now?", reads a GPS fix only
after the merchant says yes, and sends it here. The customer app's
"Itinéraire" button then opens the phone's maps app with directions to it.

Abidjan addresses are often descriptive ("face pharmacie X, Angré"), so a fix
taken in the shop is the most reliable location we can get, and the merchant
is the only person who is reliably standing there.

Guards: the venue comes from the token, never the request (a merchant can only
place their own shop); the point must be inside Côte d'Ivoire; and a fix less
precise than 100 m is refused, because it could put the shop on the wrong
street. Where the coordinates came from is recorded next to them.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import SHOP_STAFF, require_role
from ..db import get_db
from .customer import utcnow
from .payment_requests import _my_venue

router = APIRouter()

# Côte d'Ivoire, with a small margin (roughly 4.35-10.74 N, 8.6-2.49 W).
_CI_LAT = (4.0, 11.0)
_CI_LON = (-9.0, -2.0)
MAX_ACCURACY_M = 100


class VenueLocationIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # The phone's own estimate of its error radius, in metres.
    accuracy_m: float = Field(gt=0, le=10_000)


class VenueLocationOut(BaseModel):
    venue_id: int
    venue_name: str
    latitude: float | None
    longitude: float | None
    accuracy_m: int | None
    source: str | None
    set_at: str | None


def _out(venue) -> VenueLocationOut:
    return VenueLocationOut(
        venue_id=venue.id,
        venue_name=venue.name,
        latitude=float(venue.latitude) if venue.latitude is not None else None,
        longitude=float(venue.longitude) if venue.longitude is not None else None,
        accuracy_m=venue.location_accuracy_m,
        source=venue.location_source,
        set_at=venue.location_set_at.isoformat() if venue.location_set_at else None,
    )


@router.get("/merchant/venue/location", response_model=VenueLocationOut)
async def my_venue_location(db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))):
    """Whether the shop has a position yet, and how good it is."""
    return _out(await _my_venue(db, user, require_wallet=False))


@router.put("/merchant/venue/location", response_model=VenueLocationOut)
async def set_my_venue_location(
    payload: VenueLocationIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))
):
    """Save the shop's position, taken by the merchant standing in it."""
    if not (_CI_LAT[0] <= payload.latitude <= _CI_LAT[1] and _CI_LON[0] <= payload.longitude <= _CI_LON[1]):
        raise HTTPException(status_code=422, detail="Cette position n'est pas en Côte d'Ivoire.")
    if payload.accuracy_m > MAX_ACCURACY_M:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Position trop imprécise ({round(payload.accuracy_m)} m). "
                "Approchez-vous d'une porte ou d'une fenêtre et réessayez."
            ),
        )
    venue = await _my_venue(db, user, require_wallet=False)
    # Six decimals is about 11 cm: finer than any phone GPS, coarse enough to
    # store exactly.
    venue.latitude = Decimal(str(round(payload.latitude, 6)))
    venue.longitude = Decimal(str(round(payload.longitude, 6)))
    venue.location_accuracy_m = max(1, round(payload.accuracy_m))
    venue.location_source = "merchant_gps"
    venue.location_set_at = utcnow()
    await db.commit()
    await db.refresh(venue)
    return _out(venue)
