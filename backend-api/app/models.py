from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, func, Text, Boolean, Index
from sqlalchemy.orm import relationship
from .db import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_owner_created_at", "created_by", "created_at"),
        Index("ix_payments_external_status", "external_id", "status"),
    )
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Numeric, nullable=False)
    currency = Column(String(8), nullable=False)
    recipient_id = Column(String(128), nullable=False)
    country_code = Column(String(2), nullable=False, default="CI")
    provider = Column(String(64), nullable=False, default="sandbox")
    external_id = Column(String(255), nullable=True, unique=True, index=True)
    checkout_url = Column(String(1024), nullable=True)
    idempotency_key = Column(String(128), nullable=True, unique=True, index=True)
    status = Column(String(32), nullable=False, default="created", index=True)
    provider_status = Column(String(32), nullable=True)
    error_code = Column(String(64), nullable=True)
    created_by = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaymentReconciliation(Base):
    __tablename__ = "payment_reconciliations"
    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    provider = Column(String(64), nullable=False)
    provider_status = Column(String(32), nullable=False)
    amount = Column(Numeric, nullable=False)
    currency = Column(String(8), nullable=False)
    raw_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaymentRefund(Base):
    __tablename__ = "payment_refunds"
    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    amount = Column(Numeric, nullable=False)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    external_id = Column(String(255), nullable=True, unique=True)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaymentDispute(Base):
    __tablename__ = "payment_disputes"
    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    reason = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    external_id = Column(String(255), nullable=True, unique=True)
    description = Column(Text, nullable=True)
    # relationships
    transactions = relationship("Transaction", back_populates="merchant")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_merchant_timestamp", "merchant_id", "timestamp"),
        Index("ix_transactions_merchant_user_timestamp", "merchant_id", "user_id", "timestamp"),
    )
    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    user_id = Column(String(128), nullable=True, index=True)
    amount = Column(Numeric, nullable=False)
    currency = Column(String(8), nullable=False)
    type = Column(String(32), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    idempotency_key = Column(String(128), nullable=True, unique=True, index=True)
    idempotency_hash = Column(String(64), nullable=True)

    merchant = relationship("Merchant", back_populates="transactions")


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (Index("ix_consents_user_merchant_scope", "user_id", "merchant_id", "scope"),)
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    scope = Column(String(255), nullable=False)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    merchant = relationship("Merchant")


class TontineGroup(Base):
    __tablename__ = "tontine_groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    organizer_id = Column(String(128), nullable=False, index=True)
    contribution_amount = Column(Numeric, nullable=False)
    currency = Column(String(8), nullable=False, default="XOF")
    frequency = Column(String(32), nullable=False, default="monthly")
    max_members = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("TontineMember", back_populates="group")
    cycles = relationship("TontineCycle", back_populates="group")


class TontineMember(Base):
    __tablename__ = "tontine_members"
    __table_args__ = (Index("ix_tontine_members_group_user_active", "group_id", "user_id", "active"),)
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("tontine_groups.id"), nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    is_admin = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    group = relationship("TontineGroup", back_populates="members")
    contributions = relationship("Contribution", back_populates="member")


class TontineCycle(Base):
    __tablename__ = "tontine_cycles"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("tontine_groups.id"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False, default=1)
    start_at = Column(DateTime(timezone=True), nullable=True)
    end_at = Column(DateTime(timezone=True), nullable=True)
    payout_member_id = Column(Integer, ForeignKey("tontine_members.id"), nullable=True)
    status = Column(String(32), nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("TontineGroup", back_populates="cycles")
    contributions = relationship("Contribution", back_populates="cycle")


class Contribution(Base):
    __tablename__ = "tontine_contributions"
    __table_args__ = (Index("ix_contributions_group_member_paid_at", "group_id", "member_id", "paid_at"),)
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("tontine_groups.id"), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey("tontine_cycles.id"), nullable=True, index=True)
    member_id = Column(Integer, ForeignKey("tontine_members.id"), nullable=False, index=True)
    amount = Column(Numeric, nullable=False)
    currency = Column(String(8), nullable=False)
    paid_at = Column(DateTime(timezone=True), server_default=func.now())
    payment_reference = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="received")

    member = relationship("TontineMember", back_populates="contributions")
    cycle = relationship("TontineCycle", back_populates="contributions")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), nullable=False, unique=False, index=True)
    payload = Column(Text, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now())


class WebhookProcessingLog(Base):
    __tablename__ = "webhook_processing_log"
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())


class WebhookIdempotency(Base):
    __tablename__ = "webhook_idempotency"
    external_id = Column(String(255), primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)


# --- Customer side: places, on-duty pharmacies, payments, loyalty -----------
#
# Datetimes below are naive UTC. Abidjan is UTC+0 all year, so "now" on the
# server and on a customer's phone agree without conversion, and SQLite (the
# dev default) drops tzinfo anyway.


class Venue(Base):
    """A place a customer can find and pay: a maquis, a pharmacy, a shop...

    `payout_provider`/`payout_account` are the merchant's OWN mobile-money
    wallet. A customer payment goes straight there through the licensed
    aggregator; Djassa never holds the money (docs/business/CONCEPT.md § 6).
    """

    __tablename__ = "venues"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(32), nullable=False, index=True)  # a key of app.api.customer.CATEGORIES
    name = Column(String(255), nullable=False)
    commune = Column(String(64), nullable=False, index=True)
    address = Column(String(255), nullable=True)
    latitude = Column(Numeric, nullable=True)
    longitude = Column(Numeric, nullable=True)
    phone = Column(String(32), nullable=True)
    description = Column(Text, nullable=True)
    specialties = Column(String(255), nullable=True)
    opening_hours = Column(String(255), nullable=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True)
    # The login that runs this venue from the merchant app. Skeleton auth has
    # no user table, so the username is the link.
    owner_username = Column(String(128), nullable=True, index=True)
    payout_provider = Column(String(16), nullable=True)
    payout_account = Column(String(32), nullable=True)
    # Printed in the venue's payment QR code (see app/api/customer.py). Random
    # and unguessable, so a QR cannot be forged by counting up ids; rotating it
    # voids a stolen or tampered sticker.
    pay_code = Column(String(16), nullable=True, unique=True, index=True)
    # Loyalty points earned per 100 XOF paid. 0 = venue not in the programme.
    points_per_100 = Column(Integer, nullable=False, default=1)
    # Seeded demo data. Shown as such in the app so nobody mistakes a sample
    # pharmacy for a real one open tonight.
    is_sample = Column(Boolean, nullable=False, default=False)

    duties = relationship("PharmacyDuty", back_populates="venue")
    rewards = relationship("LoyaltyReward", back_populates="venue")
    deals = relationship("Deal", back_populates="venue")


class Deal(Base):
    """A time-limited offer a venue publishes ("bon plan"): a discount, a
    reduced price or something free with a purchase.

    The merchant writes and runs their own deals. `is_featured` is the paid
    publicity slot (home carousel, top of the list): only an admin sets it, so
    placement is sold, not self-granted.
    """

    __tablename__ = "deals"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    # Any combination may be set; the app shows the strongest one as the badge.
    discount_percent = Column(Integer, nullable=True)
    price = Column(Integer, nullable=True)  # XOF, the deal price
    original_price = Column(Integer, nullable=True)  # XOF, struck through
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=False, index=True)
    is_featured = Column(Boolean, nullable=False, default=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)

    venue = relationship("Venue", back_populates="deals")


class PharmacyDuty(Base):
    """One on-duty ("de garde") period. The rotation changes weekly."""

    __tablename__ = "pharmacy_duties"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=False, index=True)

    venue = relationship("Venue", back_populates="duties")


class CustomerPayment(Base):
    """A customer paying a venue with mobile money.

    Lifecycle: pending -> succeeded | failed. Only the aggregator decides the
    outcome (synchronously for the fake provider, by webhook for a real one);
    loyalty points are granted exactly once, on the transition to succeeded.
    """

    __tablename__ = "customer_payments"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String(128), nullable=False, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # XOF has no minor unit
    currency = Column(String(8), nullable=False, default="XOF")
    wallet_provider = Column(String(16), nullable=False)
    payer_msisdn = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    failure_reason = Column(String(255), nullable=True)
    provider_reference = Column(String(64), nullable=True, index=True)
    # Client-generated, so a retry after a dropped connection cannot charge twice.
    idempotency_key = Column(String(64), nullable=False, unique=True)
    points_awarded = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    venue = relationship("Venue")


class LoyaltyReward(Base):
    """Something a venue offers in exchange for points. Never cash."""

    __tablename__ = "loyalty_rewards"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    cost_points = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True)

    venue = relationship("Venue", back_populates="rewards")


class LoyaltyEntry(Base):
    """Append-only points ledger. A balance is always a SUM, never a stored total."""

    __tablename__ = "loyalty_entries"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String(128), nullable=False, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    points = Column(Integer, nullable=False)  # + earned, - redeemed
    reason = Column(String(16), nullable=False)  # "payment" | "redeem"
    payment_id = Column(Integer, ForeignKey("customer_payments.id"), nullable=True, unique=True)
    reward_id = Column(Integer, ForeignKey("loyalty_rewards.id"), nullable=True)
    voucher_code = Column(String(16), nullable=True)
    created_at = Column(DateTime, nullable=False)

    venue = relationship("Venue")
    reward = relationship("LoyaltyReward")


class PaymentRequest(Base):
    """A one-time QR the merchant shows at the counter, for a fixed amount.

    open -> processing -> paid, or back to open if the customer's wallet
    declines; open -> expired | cancelled. `processing` is taken with a
    conditional UPDATE so two customers scanning the same QR cannot both pay it.
    """

    __tablename__ = "payment_requests"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(16), nullable=False, unique=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="open", index=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    payment_id = Column(Integer, ForeignKey("customer_payments.id"), nullable=True)

    venue = relationship("Venue")
    payment = relationship("CustomerPayment")


class SupportRequest(Base):
    __tablename__ = "support_requests"
    __table_args__ = (
        Index("ix_support_requests_user_created_at", "user_id", "created_at"),
        Index("ix_support_requests_country_status", "country_code", "status"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    country_code = Column(String(2), nullable=False)
    language = Column(String(16), nullable=False)
    channel = Column(String(32), nullable=False)
    category = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="open", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IdentityProfile(Base):
    __tablename__ = "identity_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(128), nullable=False, unique=True, index=True)
    country_code = Column(String(2), nullable=False)
    phone_e164 = Column(String(16), nullable=False)
    operator = Column(String(64), nullable=False)
    verification_tier = Column(Integer, nullable=False, default=0)
    verification_status = Column(String(32), nullable=False, default="tier_0_pending")
    verification_provider = Column(String(128), nullable=True)
    attestation_reference = Column(String(255), nullable=True)
    consent_version = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
