from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WalletProvider = Literal["wave", "orange", "mtn", "moov"]


class RewardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    cost_points: int


class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    name: str
    commune: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    description: str | None = None
    specialties: str | None = None
    opening_hours: str | None = None
    points_per_100: int
    accepts_payment: bool
    is_sample: bool


class VenueDetailOut(VenueOut):
    rewards: list[RewardOut] = []
    my_points: int = 0


class OnDutyPharmacyOut(VenueOut):
    duty_starts_at: datetime
    duty_ends_at: datetime


class DutyIn(BaseModel):
    starts_at: datetime
    ends_at: datetime


class DutyOut(DutyIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    venue_id: int


class PayTargetOut(BaseModel):
    """What a scanned QR resolves to, as the SERVER knows it.

    The app shows these fields, never text read from the QR itself, so a
    forged sticker cannot display a trusted name.
    """

    venue_id: int
    name: str
    commune: str
    category: str
    is_sample: bool
    points_per_100: int
    payout_provider: str
    # Set when the QR is a merchant's payment request: the amount is fixed by
    # the merchant and the customer only confirms it.
    amount: int | None = None
    expires_at: datetime | None = None
    # Last digits only: enough for the customer to check against the sign on
    # the counter, not enough to harvest merchants' numbers.
    payout_account_masked: str


class PayCodeOut(BaseModel):
    venue_id: int
    name: str
    pay_code: str
    qr_payload: str


class PaymentIn(BaseModel):
    # The code from the venue's QR. Paying requires having scanned it: it
    # proves the customer is at the counter and picks the venue unambiguously.
    pay_code: str = Field(min_length=6, max_length=16)
    # Mobile-money wallets cap single transfers well below this; the floor
    # stops a mistyped "15" when the customer meant 1500. Required for a
    # venue's static QR; for a payment request it may be omitted, and if sent
    # must equal the requested amount.
    amount: int | None = Field(default=None, ge=100, le=2_000_000)
    wallet_provider: WalletProvider
    payer_msisdn: str = Field(max_length=24)
    idempotency_key: str = Field(min_length=8, max_length=64)

    @field_validator("payer_msisdn")
    @classmethod
    def _normalise_msisdn(cls, v: str) -> str:
        # People type "+225 07 12 34 56 78"; store "+2250712345678".
        compact = v.replace(" ", "").replace("-", "")
        digits = compact.removeprefix("+")
        if not digits.isdigit() or not 8 <= len(digits) <= 15:
            raise ValueError("numero de telephone invalide")
        return compact


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    venue_id: int
    venue_name: str
    amount: int
    currency: str
    wallet_provider: str
    status: str
    failure_reason: str | None = None
    provider_reference: str | None = None
    points_awarded: int
    created_at: datetime
    completed_at: datetime | None = None


class VenueBalanceOut(BaseModel):
    venue_id: int
    venue_name: str
    points: int
    rewards: list[RewardOut]


class LoyaltyEntryOut(BaseModel):
    id: int
    venue_id: int
    venue_name: str
    points: int
    reason: str
    voucher_code: str | None = None
    reward_title: str | None = None
    created_at: datetime


class LoyaltyOut(BaseModel):
    total_points: int
    venues: list[VenueBalanceOut]
    history: list[LoyaltyEntryOut]


class RedeemIn(BaseModel):
    reward_id: int


class RedeemOut(BaseModel):
    voucher_code: str
    reward_title: str
    venue_name: str
    points_spent: int
    remaining_points: int


class PaymentRequestIn(BaseModel):
    amount: int = Field(ge=100, le=2_000_000)


class PaymentRequestOut(BaseModel):
    id: int
    code: str
    qr_payload: str
    amount: int
    status: str  # open | processing | paid | expired | cancelled
    venue_name: str
    created_at: datetime
    expires_at: datetime
    paid_at: datetime | None = None
    wallet_provider: str | None = None
    points_awarded: int | None = None


class DayTotal(BaseModel):
    day: str  # YYYY-MM-DD, Abidjan time (= UTC)
    amount: int
    count: int


class MerchantStatsOut(BaseModel):
    """What Djassa brought in, in words a merchant uses.

    Revenue, not profit: Djassa does not know the merchant's costs (stock,
    rent, staff), so it never claims a profit figure it cannot compute.
    """

    venue_name: str
    days: int
    revenue: int
    payments: int
    average_basket: int
    customers: int
    returning_customers: int
    # Share of revenue from customers who paid more than once in the period:
    # the loyalty programme's actual effect, in money.
    returning_revenue: int
    points_issued: int
    rewards_redeemed: int
    today_revenue: int
    today_payments: int
    by_day: list[DayTotal]
    by_wallet: dict[str, int]
