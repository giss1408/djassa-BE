from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    venue_id: int
    venue_name: str
    plan: str
    status: str
    amount: int
    currency: str
    period: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    started_at: datetime | None = None
    cancelled_at: datetime | None = None
    # What this plan unlocks, so the app can show it without hardcoding the rules.
    features: list[str] = []
    max_stats_days: int | None = None


class SubscriptionIn(BaseModel):
    """An admin putting a venue on a plan."""

    plan: str
    amount: int = Field(ge=0, le=10_000_000)  # XOF per period; 0 for a comped outlet
    currency: str = "XOF"
    period: str = "monthly"
    status: str | None = None  # defaults to trialing on create, unchanged on update


class BillingPaymentIn(BaseModel):
    amount: int | None = Field(default=None, ge=0, le=10_000_000)  # defaults to the plan amount
    payment_reference: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=255)


class BillingEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    amount: int
    currency: str
    payment_reference: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    note: str | None = None
    occurred_at: datetime
    recorded_by: str


class RevenueSummaryOut(BaseModel):
    """The numbers the pilot decision gate needs, from the billing record."""

    active_paying_outlets: int
    mrr: int
    currency: str
    outlets_by_plan: dict[str, int]
    outlets_by_status: dict[str, int]
    collected_in_window: int
    window_days: int
    unpaid_invoices: int
    unpaid_amount: int
