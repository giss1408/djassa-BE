from fastapi import APIRouter, HTTPException

from ..core.countries import COUNTRIES, country_dict, get_country

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/countries")
async def list_countries():
    return {"countries": [country_dict(profile) for profile in COUNTRIES.values()]}


@router.get("/countries/{country_code}")
async def country_configuration(country_code: str):
    profile = get_country(country_code)
    if profile is None:
        raise HTTPException(status_code=404, detail="Country is not supported")
    return country_dict(profile)
