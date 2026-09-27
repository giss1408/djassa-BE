from datetime import datetime

from pydantic import BaseModel, Field


class IdentityProfileIn(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    phone_e164: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    operator: str = Field(min_length=2, max_length=64)
    consent_version: str = Field(min_length=1, max_length=64)


class IdentityProfileOut(BaseModel):
    user_id: str
    country_code: str
    phone_e164: str
    operator: str
    verification_tier: int
    verification_status: str
    verification_provider: str | None
    attestation_reference: str | None
    consent_version: str
    created_at: datetime
    updated_at: datetime


class VerificationRequestOut(BaseModel):
    user_id: str
    requested_tier: int
    status: str
    message: str
