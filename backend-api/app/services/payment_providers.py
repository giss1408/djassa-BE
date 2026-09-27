import asyncio
import os
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from ..core.countries import get_country


@dataclass(frozen=True)
class PaymentInitiation:
    external_id: str
    status: str
    checkout_url: str | None = None


@dataclass(frozen=True)
class ProviderPaymentStatus:
    external_id: str
    status: str
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class RefundResult:
    external_id: str
    status: str


class PaymentProvider(Protocol):
    name: str

    async def initiate_payment(self, *, amount: Decimal, currency: str, recipient_id: str, idempotency_key: str) -> PaymentInitiation:
        ...

    async def get_status(self, external_id: str) -> ProviderPaymentStatus:
        ...

    async def refund(self, *, external_id: str, amount: Decimal, idempotency_key: str) -> RefundResult:
        ...


class SandboxPaymentProvider:
    name = "sandbox"

    async def initiate_payment(self, *, amount: Decimal, currency: str, recipient_id: str, idempotency_key: str) -> PaymentInitiation:
        await asyncio.sleep(0)
        return PaymentInitiation(
            external_id=f"sandbox-{uuid.uuid4().hex}",
            status="pending",
            checkout_url=f"https://sandbox.invalid/pay/{idempotency_key}",
        )

    async def get_status(self, external_id: str) -> ProviderPaymentStatus:
        return ProviderPaymentStatus(external_id=external_id, status="pending", amount=Decimal("0"), currency="")

    async def refund(self, *, external_id: str, amount: Decimal, idempotency_key: str) -> RefundResult:
        await asyncio.sleep(0)
        return RefundResult(external_id=f"sandbox-refund-{uuid.uuid4().hex}", status="pending")


class ConfiguredProviderUnavailable:
    """Fail-closed placeholder until a real provider adapter is installed."""

    def __init__(self, name: str):
        self.name = name

    async def initiate_payment(self, **kwargs):
        raise RuntimeError(f"Payment provider adapter is not installed: {self.name}")

    async def get_status(self, external_id: str):
        raise RuntimeError(f"Payment provider adapter is not installed: {self.name}")

    async def refund(self, **kwargs):
        raise RuntimeError(f"Payment provider adapter is not installed: {self.name}")


def get_payment_provider(country_code: str) -> PaymentProvider:
    provider_name = os.getenv("PAYMENT_PROVIDER", "sandbox").lower()
    if provider_name == "sandbox":
        return SandboxPaymentProvider()
    profile = get_country(country_code)
    if profile is None or provider_name not in profile.payment_providers:
        raise RuntimeError(f"Payment provider {provider_name} is not enabled for {country_code}")
    # API keys and endpoints are expected to come from a secret manager.
    if not os.getenv("PAYMENT_PROVIDER_API_KEY"):
        raise RuntimeError("PAYMENT_PROVIDER_API_KEY is required for live payment providers")
    return ConfiguredProviderUnavailable(provider_name)
