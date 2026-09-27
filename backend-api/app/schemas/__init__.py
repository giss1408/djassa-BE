from pydantic import BaseModel
from datetime import datetime


class Payment(BaseModel):
    amount: float
    currency: str
    recipient_id: str


class PaymentOut(Payment):
    id: int


class Transaction(BaseModel):
    merchant_id: int
    user_id: str | None = None
    amount: float
    currency: str
    type: str


class TransactionOut(Transaction):
    id: int
    timestamp: datetime


class Merchant(BaseModel):
    id: int | None = None
    name: str
    external_id: str | None = None
    description: str | None = None


class ConsentIn(BaseModel):
    user_id: str
    merchant_id: int
    scope: str


class ConsentOut(ConsentIn):
    id: int
    granted_at: datetime
