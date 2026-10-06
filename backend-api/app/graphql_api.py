from decimal import Decimal, InvalidOperation
from typing import Optional

import strawberry
from fastapi import Request
from graphql import GraphQLError
from sqlalchemy import select
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from .api.transactions import persist_transaction, request_fingerprint, transaction_output
from .core.countries import country_dict, get_country
from .core.security import decode_access_token
from .db import AsyncSessionLocal
from .models import SaleEvent as SaleEventModel
from .models import Transaction as TransactionModel
from .models import Venue as VenueModel
from .schemas import Transaction as TransactionInput


@strawberry.type
class Country:
    code: str
    name: str
    currency: str
    phone_prefixes: list[str]
    languages: list[str]
    support_channels: list[str]
    payment_providers: list[str]


@strawberry.type
class Transaction:
    """DEPRECATED: a row of the old merchant-declared stream.

    Superseded by `SaleEvent`, which labels its evidence class. Kept while
    `transactions` exists for rollback safety; use `mySales`.
    """

    id: int
    merchant_id: int
    user_id: Optional[str]
    amount: str
    currency: str
    type: str
    timestamp: str


@strawberry.type
class SaleEvent:
    """One sale, with the evidence behind it stated.

    `source` is the field that matters: `mobile_money_confirmed` means an
    aggregator confirmed the money moved, `cash_declared` means the merchant
    said so. Both are real business; they are never the same evidence
    (docs/optimization_claude_hossouko.md, finding 2).
    """

    id: int
    venue_id: Optional[int]
    source: str
    amount: str
    currency: str
    type: Optional[str]
    occurred_at: str
    recorded_at: str
    customer_id: Optional[str]


@strawberry.input
class TransactionOperation:
    idempotency_key: str
    merchant_id: int
    amount: str
    currency: str
    type: str


@strawberry.type
class SyncResult:
    idempotency_key: str
    status: str
    transaction: Optional[Transaction] = None
    error: Optional[str] = None


def to_country(profile) -> Country:
    data = country_dict(profile)
    return Country(
        code=data["code"],
        name=data["name"],
        currency=data["currency"],
        phone_prefixes=list(data["phone_prefixes"]),
        languages=list(data["languages"]),
        support_channels=list(data["support_channels"]),
        payment_providers=list(data["payment_providers"]),
    )


def to_sale_event(value: SaleEventModel) -> SaleEvent:
    return SaleEvent(
        id=value.id,
        venue_id=value.venue_id,
        source=value.source,
        amount=str(value.amount),
        currency=value.currency,
        type=value.type,
        occurred_at=value.occurred_at.isoformat(),
        recorded_at=value.recorded_at.isoformat(),
        customer_id=value.customer_id,
    )


def to_transaction(value: TransactionModel) -> Transaction:
    return Transaction(
        id=value.id,
        merchant_id=value.merchant_id,
        user_id=value.user_id,
        amount=str(value.amount),
        currency=value.currency,
        type=value.type,
        timestamp=value.timestamp.isoformat(),
    )


def authenticated_user(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise GraphQLError("Authentication required")
    payload = decode_access_token(token)
    subject = payload.get("sub") if payload else None
    if not subject or not isinstance(subject, str):
        raise GraphQLError("Invalid authentication credentials")
    return subject


@strawberry.type
class Query:
    @strawberry.field
    async def countries(self) -> list[Country]:
        from .core.countries import COUNTRIES
        return [to_country(profile) for profile in COUNTRIES.values()]

    @strawberry.field
    async def country(self, code: str) -> Country:
        profile = get_country(code)
        if profile is None:
            raise GraphQLError("Country is not supported")
        return to_country(profile)

    @strawberry.field
    async def my_sales(self, info: Info, limit: int = 50) -> list[SaleEvent]:
        """The signed-in merchant's own sales, from the merged stream.

        No `merchant_id` argument: the venue comes from the token, so there is
        nothing to tamper with. Quarantined rows are excluded -- they belong to
        no identifiable venue, so they are nobody's to read.
        """
        user_id = authenticated_user(info.context["request"])
        limit = max(1, min(limit, 100))
        async with AsyncSessionLocal() as db:
            venue = (
                await db.execute(select(VenueModel).where(VenueModel.owner_username == user_id))
            ).scalars().first()
            if venue is None:
                raise GraphQLError("This account is not linked to a venue")
            result = await db.execute(
                select(SaleEventModel)
                .where(
                    SaleEventModel.venue_id == venue.id,
                    SaleEventModel.status == "recorded",
                )
                .order_by(SaleEventModel.occurred_at.desc(), SaleEventModel.id.desc())
                .limit(limit)
            )
            return [to_sale_event(value) for value in result.scalars().all()]

    @strawberry.field(deprecation_reason="Use mySales: the declared stream is merged into sale_events")
    async def my_transactions(self, info: Info, merchant_id: int, limit: int = 50) -> list[Transaction]:
        user_id = authenticated_user(info.context["request"])
        limit = max(1, min(limit, 100))
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TransactionModel)
                .where(TransactionModel.merchant_id == merchant_id, TransactionModel.user_id == user_id)
                .order_by(TransactionModel.timestamp.desc())
                .limit(limit)
            )
            return [to_transaction(value) for value in result.scalars().all()]


@strawberry.type
class Mutation:
    @strawberry.mutation(
        deprecation_reason="Use POST /api/merchant/sales/sync: the venue must come from the token, not the body"
    )
    async def sync_transactions(self, info: Info, operations: list[TransactionOperation]) -> list[SyncResult]:
        if not 1 <= len(operations) <= 50:
            raise GraphQLError("Between 1 and 50 operations are required")
        user_id = authenticated_user(info.context["request"])
        results = []
        async with AsyncSessionLocal() as db:
            for operation in operations:
                try:
                    amount = Decimal(operation.amount)
                    payload = TransactionInput(
                        merchant_id=operation.merchant_id,
                        amount=amount,
                        currency=operation.currency,
                        type=operation.type,
                    )
                    value, already_processed = await persist_transaction(
                        payload, user_id, db, operation.idempotency_key
                    )
                    await db.commit()
                    await db.refresh(value)
                    results.append(SyncResult(
                        idempotency_key=operation.idempotency_key,
                        status="already_processed" if already_processed else "accepted",
                        transaction=to_transaction(value),
                    ))
                except (InvalidOperation, ValueError):
                    await db.rollback()
                    results.append(SyncResult(
                        idempotency_key=operation.idempotency_key,
                        status="rejected",
                        error="invalid amount",
                    ))
                except GraphQLError:
                    await db.rollback()
                    raise
                except Exception:
                    await db.rollback()
                    results.append(SyncResult(
                        idempotency_key=operation.idempotency_key,
                        status="rejected",
                        error="operation could not be processed",
                    ))
        return results


schema = strawberry.Schema(query=Query, mutation=Mutation)
router = GraphQLRouter(schema)
