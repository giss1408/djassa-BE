from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field


class Payment(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=8)
    recipient_id: str = Field(min_length=1, max_length=128)
    country_code: str = Field(default="CI", min_length=2, max_length=2)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class PaymentOut(Payment):
    id: int
    provider: str
    external_id: str | None
    status: str
    checkout_url: str | None = None


class RefundRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    idempotency_key: str = Field(min_length=8, max_length=128)


class RefundOut(BaseModel):
    id: int
    payment_id: int
    amount: Decimal
    external_id: str | None
    status: str


class DisputeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class Transaction(BaseModel):
    merchant_id: int
    user_id: str | None = None
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=8)
    type: str = Field(min_length=1, max_length=32)


class TransactionOut(Transaction):
    id: int
    timestamp: datetime


class TransactionSyncItem(Transaction):
    idempotency_key: str = Field(min_length=8, max_length=128)


class SyncRequest(BaseModel):
    operations: List[TransactionSyncItem] = Field(min_length=1, max_length=50)


class SyncOperationResult(BaseModel):
    idempotency_key: str
    status: str
    transaction: TransactionOut | None = None
    error: str | None = None


class SyncResponse(BaseModel):
    results: List[SyncOperationResult]


class Merchant(BaseModel):
    id: int | None = None
    name: str
    external_id: str | None = None
    description: str | None = None


class ConsentIn(BaseModel):
    user_id: str | None = None
    merchant_id: int
    scope: str = Field(min_length=1, max_length=255)


class ConsentOut(ConsentIn):
    id: int
    granted_at: datetime
