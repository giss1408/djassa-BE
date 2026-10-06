from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .media import MediaOut

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
    # The first photo's 320 px thumbnail, for list cards. None without photos.
    cover_url: str | None = None


class CategoryOut(BaseModel):
    key: str
    label: str
    plural: str


class DealOut(BaseModel):
    id: int
    venue_id: int
    venue_name: str
    venue_category: str
    venue_commune: str
    title: str
    description: str | None = None
    discount_percent: int | None = None
    price: int | None = None
    original_price: int | None = None
    ribbon: str = "bon_plan"
    starts_at: datetime
    ends_at: datetime
    is_featured: bool
    is_sample: bool


class DealIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    discount_percent: int | None = Field(default=None, ge=1, le=90)
    price: int | None = Field(default=None, ge=0, le=10_000_000)
    original_price: int | None = Field(default=None, ge=1, le=10_000_000)
    # Corner banner on the deal's image (models.Deal.ribbon).
    ribbon: Literal["bon_plan", "flash", "promo"] = "bon_plan"
    starts_at: datetime | None = None  # defaults to now
    ends_at: datetime

    @model_validator(mode="after")
    def _coherent(self):
        if self.price is not None and self.original_price is not None and self.price >= self.original_price:
            raise ValueError("le prix promo doit etre inferieur au prix d'origine")
        return self


class DealFeatureIn(BaseModel):
    is_featured: bool


class PlacementIn(BaseModel):
    """An admin selling the featured slot for a dated window."""

    starts_at: datetime | None = None  # defaults to now
    ends_at: datetime
    price: int = Field(ge=0, le=10_000_000)  # 0 is allowed: a comped slot is still a record
    currency: str = "XOF"


class PlacementPaidIn(BaseModel):
    payment_reference: str | None = Field(default=None, max_length=64)


class PlacementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    deal_id: int
    venue_id: int
    venue_name: str
    deal_title: str
    starts_at: datetime
    ends_at: datetime
    price: int
    currency: str
    status: str
    paid_at: datetime | None = None
    payment_reference: str | None = None
    created_by: str
    created_at: datetime
    is_live: bool  # active AND inside its window right now


class VenueDetailOut(VenueOut):
    rewards: list[RewardOut] = []
    deals: list[DealOut] = []
    my_points: int = 0
    # Photos and videos, ready ones only, in the shop's order.
    media: list[MediaOut] = []


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
    # Set while a wallet checkout awaits the customer's approval: the app
    # opens it (Wave) and then polls GET /customer/payments/{id}.
    checkout_url: str | None = None
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


class CounterCustomerIn(BaseModel):
    """A customer identified at the counter by phone. POST, not a query
    string, so the number stays out of URLs and access logs."""

    phone: str = Field(min_length=6, max_length=32)


class CounterLoyaltyOut(BaseModel):
    customer: str  # masked
    points: int
    rewards: list[RewardOut]


class CounterRedeemIn(CounterCustomerIn):
    reward_id: int


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
    # --- The merged stream (app/services/revenue.py) --------------------------
    #
    # `revenue` above stays what it always was: money that actually arrived
    # through Djassa, so no existing client reads a different number than
    # before. The fields below add the cash the merchant recorded themselves,
    # labelled as such -- an aggregator confirmation and a typed figure are
    # never summed into one unqualified total.
    turnover: int  # confirmed + declared
    confirmed_revenue: int  # = revenue; named for what it is evidentially
    declared_revenue: int  # cash the merchant recorded; unverified
    declared_sales: int
    # 0.0-1.0. The merchant's own reason to push customers to digital payment:
    # this is the number a lender reads.
    verified_share: float
    # Active days / days in the window.
    regularity: float


class SaleIn(BaseModel):
    """A cash sale the merchant recorded at the counter.

    No `merchant_id` and no `venue_id`: the venue comes from the token. That
    absence is the fix -- the old declared stream took the id from the body, so
    a client could name any merchant, and the server created one if it did not
    exist.
    """

    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="XOF", min_length=3, max_length=8)
    type: str = Field(default="sale", min_length=1, max_length=32)
    # Client-generated before the first send, reused for every retry: an
    # offline queue cannot tell a lost request from a lost response.
    idempotency_key: str = Field(min_length=8, max_length=128)
    # When the merchant recorded it on the device. A sale queued overnight
    # belongs to the day it was made, not the day it synced.
    occurred_at: datetime | None = None
    # The customer's number, as typed at the counter. Optional: most cash sales
    # are anonymous. When present, the customer earns this venue's points on
    # the sale, keyed on the normalised number (app/core/phone.py).
    customer_phone: str | None = Field(default=None, max_length=32)
    # The merchant asked and the customer agreed that Djassa keeps their
    # number for points. Needed the first time a number is used; a number
    # that already has consent (app or another counter) does not need it.
    customer_consent: bool = False


class SaleOut(BaseModel):
    id: int
    venue_id: int | None
    source: str
    amount: Decimal
    currency: str
    type: str | None
    occurred_at: datetime
    recorded_at: datetime
    idempotency_key: str
    # Points the customer earned on this sale, and the number they went to,
    # masked ("07 •• •• 56 78") so the full number is not echoed back.
    points_awarded: int = 0
    customer: str | None = None


class SaleSyncIn(BaseModel):
    """A batch from the offline queue. Capped like the old sync endpoint."""

    operations: list[SaleIn] = Field(min_length=1, max_length=50)


class SaleSyncResult(BaseModel):
    idempotency_key: str
    status: str  # accepted | already_processed | rejected
    sale: SaleOut | None = None
    error: str | None = None


class SaleSyncOut(BaseModel):
    results: list[SaleSyncResult]


class LoyaltyConsentIn(BaseModel):
    # The wording version the app displayed (app/services/loyalty_consent.py).
    consent_version: str = Field(min_length=1, max_length=64)


class LoyaltyConsentOut(BaseModel):
    active: bool
    source: str | None = None
    consent_version: str | None = None
    granted_at: datetime | None = None
    # The version the server currently expects, so an app can tell whether
    # the text it shows is the one on file.
    current_version: str


class LoyaltyWithdrawOut(BaseModel):
    points_erased: int
