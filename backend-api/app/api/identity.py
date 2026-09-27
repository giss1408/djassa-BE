from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.countries import get_country
from ..core.identity import VerificationTier
from ..core.security import get_current_user
from ..db import get_db
from ..models import IdentityProfile
from ..schemas.identity import IdentityProfileIn, IdentityProfileOut, VerificationRequestOut

router = APIRouter(prefix="/identity", tags=["identity"])


def output(profile: IdentityProfile) -> IdentityProfileOut:
    return IdentityProfileOut(
        user_id=profile.user_id,
        country_code=profile.country_code,
        phone_e164=profile.phone_e164,
        operator=profile.operator,
        verification_tier=profile.verification_tier,
        verification_status=profile.verification_status,
        verification_provider=profile.verification_provider,
        attestation_reference=profile.attestation_reference,
        consent_version=profile.consent_version,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post("/profile", response_model=IdentityProfileOut, status_code=201)
async def create_identity_profile(payload: IdentityProfileIn, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    profile = get_country(payload.country_code)
    if profile is None:
        raise HTTPException(status_code=422, detail="Country is not supported")
    if not any(payload.phone_e164.startswith(prefix) for prefix in profile.phone_prefixes):
        raise HTTPException(status_code=422, detail="Phone prefix does not match country")
    existing_result = await db.execute(select(IdentityProfile).where(IdentityProfile.user_id == user["username"]))
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Identity profile already exists")
    identity = IdentityProfile(
        user_id=user["username"],
        country_code=profile.code,
        phone_e164=payload.phone_e164,
        operator=payload.operator.lower(),
        verification_tier=int(VerificationTier.TIER_0),
        verification_status="tier_0_verified",
        consent_version=payload.consent_version,
    )
    db.add(identity)
    await db.commit()
    await db.refresh(identity)
    return output(identity)


@router.get("/me", response_model=IdentityProfileOut | None)
async def get_identity_profile(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(select(IdentityProfile).where(IdentityProfile.user_id == user["username"]))
    profile = result.scalar_one_or_none()
    return output(profile) if profile else None


@router.post("/verification/{tier}", response_model=VerificationRequestOut)
async def request_verification(tier: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if tier not in {int(VerificationTier.TIER_1), int(VerificationTier.TIER_2)}:
        raise HTTPException(status_code=422, detail="Only Tier 1 or Tier 2 verification can be requested")
    result = await db.execute(select(IdentityProfile).where(IdentityProfile.user_id == user["username"]))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=409, detail="Create a Tier 0 identity profile first")
    if profile.verification_tier >= tier:
        return VerificationRequestOut(user_id=profile.user_id, requested_tier=tier, status="already_verified", message="Verification tier already satisfied")
    return VerificationRequestOut(
        user_id=profile.user_id,
        requested_tier=tier,
        status="provider_required",
        message="A licensed identity provider must complete this verification; client claims are not accepted.",
    )