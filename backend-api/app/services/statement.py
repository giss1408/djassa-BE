"""The revenue statement: a signed attestation, not a CSV dump.

No microfinance institution wants 10,000 raw rows. They want something a credit
officer can read in a minute and a compliance officer can verify was not edited
after issue: period, monthly turnover, verified share, regularity, seasonality,
customer concentration, the consent it rests on, and a signature
(docs/optimization_claude_hossouko.md, optimization C).

## What the signature is and is not

A detached HMAC-SHA256 over a canonical serialization of the payload, keyed on
`HOSSOUKO_STATEMENT_SECRET`. That makes it **tamper-evident**: a merchant who
edits a figure before forwarding the file produces a payload whose signature no
longer verifies, and `POST /api/statements/verify` says so.

It is deliberately *not* a public-key signature. HMAC means a verifier must ask
Hossouko (or hold the shared secret), so it proves "this is the document Hossouko
issued", not "this is Hossouko's document and only Hossouko could have made it".
That is the right trade for a pilot -- no key distribution, no PKI -- but it is a
one-line swap to Ed25519 the moment a partner wants to verify offline, which is
why the payload carries `algorithm` and `key_id`.

## What the numbers mean

Every figure is a SUM over `sale_events`, so a statement reconciles with the
stream by construction rather than by a second code path that could drift. The
confirmed and declared halves are always reported separately: an aggregator
confirmation and a merchant's typed figure are not the same evidence, and a
document that blurs them is the one thing a partner audit would find.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from . import revenue as revenue_service
from .revenue import RevenueProfile

# Bumped when the meaning of a field changes, so a partner holding an old
# statement knows which rules produced it. Never reuse a version for new
# semantics: a figure that quietly changed meaning is worse than a new field.
SCHEMA_VERSION = "hossouko.revenue-statement.v1"

ALGORITHM = "HMAC-SHA256"

_ENV_SECRET = "HOSSOUKO_STATEMENT_SECRET"


class StatementSecretMissing(RuntimeError):
    """Raised rather than falling back to a default or an unsigned statement.

    An unsigned attestation is a spreadsheet with a logo: it would be handed to
    a lender looking exactly as official as a real one. Failing closed is the
    only safe behaviour.
    """


def _secret() -> bytes:
    value = os.getenv(_ENV_SECRET) or os.getenv("HOSSOUKO_SECRET_KEY")
    if not value:
        raise StatementSecretMissing(
            f"{_ENV_SECRET} must be set to issue a revenue statement"
        )
    return value.encode()


def key_id() -> str:
    """A short, non-secret fingerprint of the signing key.

    So a verifier can tell "signed with a key I do not have" apart from
    "tampered with", and so a key rotation is diagnosable instead of looking
    like a forgery. A hash of the key, never the key.
    """
    return hashlib.sha256(b"hossouko-statement-key-id:" + _secret()).hexdigest()[:16]


def canonical(payload: dict) -> bytes:
    """The exact bytes that are signed.

    Sorted keys, no insignificant whitespace, every number already a string in
    the payload. If this serialization is not byte-stable, two verifiers reach
    different answers about the same document -- so nothing here may depend on
    dict ordering or float formatting.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign(payload: dict) -> str:
    return hmac.new(_secret(), canonical(payload), hashlib.sha256).hexdigest()


def verify(payload: dict, signature: str) -> bool:
    """Whether `signature` is the one Hossouko issued for `payload`.

    `compare_digest`, not `==`: a byte-at-a-time comparison leaks where a forged
    signature first differs, which is enough to construct a valid one.
    """
    try:
        expected = sign(payload)
    except StatementSecretMissing:
        return False
    return hmac.compare_digest(expected, signature or "")


def _money(value: Decimal | int) -> str:
    """Amounts travel as strings, in one canonical spelling.

    A JSON number would be a float in most readers, and a lender reconciling a
    turnover figure against a bank statement must not meet 2999.9999999.

    The normalization is not cosmetic: Postgres and SQLite hand back the same
    amount with different scales (`7000` vs `7000.0000000000`), and since these
    bytes are what gets signed, two databases would otherwise produce different
    signatures for the same business. Trailing zeros go, the integral form stays
    plain (never `7E+3`), and the value is unchanged.
    """
    amount = Decimal(value).normalize()
    if amount == amount.to_integral_value():
        amount = amount.to_integral_value()
    return format(amount, "f")


def build_payload(
    profile: RevenueProfile,
    *,
    issued_at: datetime,
    issued_to: str,
    consent_reference: str | None,
    quarantined_excluded: int,
) -> dict:
    """The signed part of a statement. Nothing outside this dict is attested."""
    return {
        "schema_version": SCHEMA_VERSION,
        "issuer": "Hossouko",
        "issued_at": issued_at.isoformat(),
        "issued_to": issued_to,
        "venue": {"id": profile.venue_id, "name": profile.venue_name},
        "period": {
            "start": profile.period_start.date().isoformat(),
            "end": profile.period_end.date().isoformat(),
            "days": profile.period_days,
        },
        "currency": profile.currency,
        "turnover": {
            "total": _money(profile.total),
            # The distinction the whole document exists to make.
            "mobile_money_confirmed": _money(profile.confirmed_total),
            "cash_declared": _money(profile.declared_total),
            "verified_share": profile.verified_share,
        },
        "volume": {
            "sales": profile.count,
            "confirmed_sales": profile.confirmed_count,
            "declared_sales": profile.declared_count,
            "average_ticket": _money(profile.average_ticket),
        },
        "activity": {
            "active_days": profile.active_days,
            "regularity": profile.regularity,
            "seasonality": profile.seasonality,
            "monthly_turnover": {month: _money(total) for month, total in sorted(profile.by_month.items())},
        },
        "customers": {
            "identified": profile.customers,
            "returning": profile.returning_customers,
            # Concentration, not identity: no customer is named anywhere in a
            # statement, so issuing one needs no customer's consent.
            "top_customer_share": profile.top_customer_share,
        },
        "data_quality": {
            "median_recording_lag_hours": profile.median_recording_lag_hours,
            # Declared sales the migration could not attach to a venue. Stated
            # rather than omitted: a reader is entitled to know the stream had
            # rows this statement does not account for.
            "quarantined_events_excluded": quarantined_excluded,
        },
        "consent_reference": consent_reference,
        "disclaimer": (
            "Hossouko n'est ni preteur ni etablissement de paiement et ne detient aucun fonds. "
            "Les montants 'cash_declared' sont declares par le commercant et non verifies par un tiers."
        ),
    }


def envelope(payload: dict) -> dict:
    """The document as issued: the payload, plus how to check it."""
    return {
        "payload": payload,
        "signature": {
            "algorithm": ALGORITHM,
            "key_id": key_id(),
            "value": sign(payload),
            "verify_with": "POST /api/statements/verify",
        },
    }


async def quarantined_count_for(db: AsyncSession, venue: models.Venue) -> int:
    """Quarantined events that plausibly belong to this venue.

    Matched on the legacy merchant id, which is the only thread back: the
    migration refused to resolve these, so this is "rows that may be yours",
    never "rows that are yours".
    """
    if venue.merchant_id is None:
        return 0
    return int(
        (
            await db.execute(
                select(func.count(models.SaleEvent.id)).where(
                    models.SaleEvent.status == "quarantined",
                    models.SaleEvent.legacy_merchant_id == venue.merchant_id,
                )
            )
        ).scalar_one()
    )


async def build(
    db: AsyncSession,
    *,
    venue: models.Venue,
    since: datetime,
    until: datetime,
    issued_at: datetime,
    issued_to: str,
    consent_reference: str | None = None,
) -> tuple[dict, RevenueProfile]:
    """Issue a statement for a venue and a period. Returns (envelope, profile)."""
    profile = await revenue_service.profile(db, venue=venue, since=since, until=until)
    payload = build_payload(
        profile,
        issued_at=issued_at,
        issued_to=issued_to,
        consent_reference=consent_reference,
        quarantined_excluded=await quarantined_count_for(db, venue),
    )
    return envelope(payload), profile
