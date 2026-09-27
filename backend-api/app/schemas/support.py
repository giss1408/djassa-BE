from datetime import datetime

from pydantic import BaseModel, Field


class SupportRequestIn(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    language: str = Field(min_length=2, max_length=16)
    channel: str = Field(min_length=2, max_length=32)
    category: str = Field(min_length=2, max_length=64)
    message: str = Field(min_length=1, max_length=4000)


class SupportRequestOut(BaseModel):
    id: int
    status: str
    country_code: str
    language: str
    channel: str
    category: str
    message: str
    confirmation: str
    created_at: datetime
