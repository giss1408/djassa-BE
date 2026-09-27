from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal
from pydantic import Field


class TontineGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    organizer_id: str | None = None
    contribution_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Optional[str] = Field(default="XOF", min_length=3, max_length=8)
    frequency: Optional[str] = Field(default="monthly", min_length=1, max_length=32)
    max_members: Optional[int] = Field(default=None, ge=1, le=10000)
    description: Optional[str] = Field(default=None, max_length=2000)


class TontineGroupOut(BaseModel):
    id: int
    name: str
    organizer_id: str
    contribution_amount: Decimal
    currency: str
    frequency: str
    max_members: Optional[int]
    description: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class JoinRequest(BaseModel):
    user_id: str | None = None


class ContributionCreate(BaseModel):
    user_id: str | None = None
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    payment_reference: Optional[str] = Field(default=None, max_length=255)


class CycleOut(BaseModel):
    id: int
    cycle_number: int
    start_at: Optional[datetime]
    end_at: Optional[datetime]
    status: str

    model_config = ConfigDict(from_attributes=True)
