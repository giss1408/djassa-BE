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


def get_provider() -> MobileMoneyProvider:
    name = os.getenv("MOBILE_MONEY_PROVIDER", "fake")
    if name == "fake":
        # A fake provider in production would "confirm" payments no one made.
        if os.getenv("DJASSA_ENV") == "production":
            raise RuntimeError("MOBILE_MONEY_PROVIDER=fake is refused when DJASSA_ENV=production")
        return FakeProvider()
    raise RuntimeError(f"Unknown or unimplemented MOBILE_MONEY_PROVIDER: {name!r}")
