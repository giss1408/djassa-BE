"""Mobile-money payment initiation, behind one interface.

Djassa is an orchestrator, not a holder of funds: a provider moves money from
the customer's wallet directly to the venue's own payout wallet through a
licensed aggregator (CinetPay covers Wave, Orange Money, MTN MoMo and Moov in
one API — see docs/business/CONCEPT.md § 6). Nothing in here may route money through an
account Djassa controls; that would be deposit-taking without a BCEAO licence.

`MOBILE_MONEY_PROVIDER` selects the implementation. (Distinct from
`PAYMENT_PROVIDER`, which configures the payment orchestration in
payment_providers.py: one variable cannot pick both.)

* ``fake`` (default) — decides instantly, for development and demos. A payer
  number ending in ``0000`` is declined, so the failure path can be exercised.
* ``wave`` — option B of the pilot: a venue that connected its own Wave
  Business account (app/api/wave.py) is paid through a Wave checkout created
  with the merchant's key, so the money lands in the merchant's wallet. The
  result is "pending" with a launch URL the customer's phone opens; Wave's
  webhook (or a status refresh) settles it. Venues without a connected account
  fall back to ``fake`` outside production and are refused in production.
* ``cinetpay`` — not implemented yet; needs a sandbox API key and site ID.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class InitiationResult:
    # "succeeded" and "failed" are final; "pending" means the aggregator will
    # report the outcome later by webhook.
    status: str
    reference: str
    failure_reason: str | None = None
    # For a redirect wallet (Wave checkout): the page the customer's phone
    # must open to approve the payment in the wallet app.
    launch_url: str | None = None


class MobileMoneyProvider:
    name = "base"

    async def initiate(
        self,
        *,
        amount: int,
        currency: str,
        wallet_provider: str,
        payer_msisdn: str,
        payout_provider: str,
        payout_account: str,
        idempotency_key: str,
    ) -> InitiationResult:
        raise NotImplementedError


class FakeProvider(MobileMoneyProvider):
    name = "fake"

    async def initiate(self, *, payer_msisdn: str, **_) -> InitiationResult:
        reference = f"FAKE-{uuid.uuid4().hex[:12].upper()}"
        if payer_msisdn.replace(" ", "").endswith("0000"):
            return InitiationResult("failed", reference, "Paiement refuse par le portefeuille (test)")
        return InitiationResult("succeeded", reference)


class ProviderUnavailable(RuntimeError):
    """This venue cannot be paid with this wallet through Djassa yet."""


def public_base_url() -> str:
    """Where Wave sends the customer's browser back after the payment.
    Render sets RENDER_EXTERNAL_URL for every web service."""
    return (os.getenv("DJASSA_PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8000").rstrip("/")


class WaveProvider(MobileMoneyProvider):
    """Checkout with the merchant's own Wave key (never Djassa's)."""

    name = "wave"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def initiate(
        self, *, amount: int, currency: str, payer_msisdn: str, idempotency_key: str, **_
    ) -> InitiationResult:
        from ..core.phone import InvalidPhone, normalize_phone
        from . import wave  # local: keeps httpx out of the fake path's imports

        try:
            payer = normalize_phone(payer_msisdn)
        except InvalidPhone:
            payer = None  # an unusual number: let any Wave wallet pay
        base = public_base_url()
        try:
            session = await wave.client_for(self._api_key).create_checkout(
                amount=amount,
                currency=currency,
                client_reference=idempotency_key,
                success_url=f"{base}/wave/return?result=ok",
                error_url=f"{base}/wave/return?result=error",
                restrict_payer_mobile=payer,
            )
        except wave.WaveError as exc:
            # No session means nothing the customer could pay: a safe final failure.
            return InitiationResult("failed", "", str(exc))
        return InitiationResult("pending", session.id, launch_url=session.launch_url)


async def provider_for(db, venue, wallet_provider: str) -> MobileMoneyProvider:
    """The provider for one payment: the venue's own Wave account when the
    customer pays with Wave and the merchant connected one, else the default."""
    if wallet_provider == "wave":
        from sqlalchemy import select

        from .. import models
        from ..core.secretbox import SecretUnavailable, unseal

        account = (
            await db.execute(select(models.WaveAccount).where(models.WaveAccount.venue_id == venue.id))
        ).scalar_one_or_none()
        if account is not None and account.api_key_sealed is None and os.getenv("DJASSA_ENV") == "production":
            # Points-only connection: no key to create a checkout with. The
            # customer pays the shop's own Wave QR and the points still come.
            raise ProviderUnavailable(
                "Payez avec le QR Wave du commerce : vos points arrivent automatiquement."
            )
        if account is not None and account.api_key_sealed is not None:
            try:
                return WaveProvider(unseal(account.api_key_sealed))
            except SecretUnavailable as exc:
                raise ProviderUnavailable(
                    "La connexion Wave de ce commerce doit etre refaite par le commercant."
                ) from exc
    name = os.getenv("MOBILE_MONEY_PROVIDER", "fake")
    if name == "wave":
        if os.getenv("DJASSA_ENV") == "production":
            raise ProviderUnavailable(
                "Ce commerce n'accepte pas encore ce portefeuille via Djassa. Payez au comptoir."
            )
        return FakeProvider()
    return get_provider()


def get_provider() -> MobileMoneyProvider:
    name = os.getenv("MOBILE_MONEY_PROVIDER", "fake")
    if name == "fake":
        # A fake provider in production would "confirm" payments no one made.
        if os.getenv("DJASSA_ENV") == "production":
            raise RuntimeError("MOBILE_MONEY_PROVIDER=fake is refused when DJASSA_ENV=production")
        return FakeProvider()
    raise RuntimeError(f"Unknown or unimplemented MOBILE_MONEY_PROVIDER: {name!r}")
