"""What a venue's own event stream says about its business.

This is the module the merged stream pays for. Because every sale now carries an
evidence label, the share of a venue's turnover that an aggregator confirmed is a
single query -- and it is the figure **no competitor in Cote d'Ivoire can
currently produce**, because nobody else holds both halves
(docs/optimization_claude_fidelia.md, optimization B).

Two audiences, one computation:

* The **merchant** sees their verified share, which gives *them* a reason to push
  customers toward digital payment. That is the behaviour change the concept
  needs, merchant-driven rather than Fidelia-driven.
* An **underwriter** sees regularity and concentration, which is the actual
  question behind "is this business real" -- and the signed statement
  (app/services/statement.py) is built on exactly these numbers.

Quarantined events are excluded everywhere: they are recorded amounts that belong
to no identifiable venue, and adding them to somebody's revenue would be a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from .sale_events import CONFIRMED, RECORDED


@dataclass(frozen=True)
class DayBucket:
    day: str
    amount: Decimal
    count: int
    confirmed_amount: Decimal


@dataclass
class RevenueProfile:
    """Everything derivable from one venue's events over one window."""

    venue_id: int
    venue_name: str
    period_start: datetime
    period_end: datetime
    currency: str
    total: Decimal
    confirmed_total: Decimal
    declared_total: Decimal
    count: int
    confirmed_count: int
    declared_count: int
    # Active days / days in the period. An underwriter reads this as "does this
    # business actually trade", which no single monthly total answers.
    active_days: int
    period_days: int
    customers: int
    returning_customers: int
    # Share of confirmed turnover taken by the single largest identified
    # customer. High concentration means the revenue is one relationship, not a
    # market -- which changes what the history is worth as evidence.
    top_customer_share: float
    # Median gap in hours between a sale happening and reaching us. The offline
    # window, reported rather than hidden: a queue that drains within the day is
    # normal, a month-old batch means the figures arrived in bulk.
    median_recording_lag_hours: float
    by_day: list[DayBucket] = field(default_factory=list)
    by_month: dict[str, Decimal] = field(default_factory=dict)

    @property
    def verified_share(self) -> float:
        """Confirmed turnover / total turnover, 0.0 to 1.0.

        Zero turnover reports 0.0, not 1.0: a venue that sold nothing has
        verified nothing, and the friendlier rounding would flatter an empty
        history in the one document a lender reads.
        """
        if self.total <= 0:
            return 0.0
        return round(float(self.confirmed_total / self.total), 4)

    @property
    def regularity(self) -> float:
        if self.period_days <= 0:
            return 0.0
        return round(self.active_days / self.period_days, 4)

    @property
    def average_ticket(self) -> Decimal:
        if self.count == 0:
            return Decimal(0)
        return (self.total / self.count).quantize(Decimal(1))

    @property
    def seasonality(self) -> float:
        """Spread of monthly turnover, as max/min over the months present.

        1.0 is flat. A high number is not a problem to hide -- a maquis busy in
        December is normal -- but a lender sizing a repayment schedule needs to
        know the trough, and one monthly average conceals it.
        """
        months = [m for m in self.by_month.values() if m > 0]
        if len(months) < 2:
            return 1.0
        return round(float(max(months) / min(months)), 2)


class TooManyEvents(RuntimeError):
    """More events in the window than a single in-memory pass will take.

    Raised rather than truncated, and that distinction is the whole point: a
    partial set still produces a *plausible* total, and the statement signs
    whatever total it is given. A signed document understating a merchant's
    turnover because a query hit a limit is the worst failure this code has, so
    the aggregation refuses instead of quietly answering.
    """

    def __init__(self, venue_id: int, limit: int):
        self.venue_id = venue_id
        self.limit = limit
        super().__init__(f"venue {venue_id} has more than {limit} events in the window")


# Generous enough that no pilot venue reaches it (a maquis at 40 sales/day needs
# ~3.5 years), small enough that one request cannot exhaust the process. When a
# real venue does hit it, the aggregation moves to SQL -- it is not raised.
MAX_EVENTS_PER_WINDOW = 50_000


async def events_in_window(
    db: AsyncSession,
    venue_id: int,
    since: datetime,
    until: datetime,
    limit: int | None = None,
) -> list[models.SaleEvent]:
    """Recorded events for a venue in [since, until].

    Ordered by occurrence, and quarantined rows are filtered out here so no
    caller has to remember to. Raises `TooManyEvents` rather than truncating --
    see that class for why.

    `limit` defaults to `MAX_EVENTS_PER_WINDOW` read at call time, not bound as a
    default argument, so the module-level cap can be adjusted in one place.
    """
    if limit is None:
        limit = MAX_EVENTS_PER_WINDOW
    events = list(
        (
            await db.execute(
                select(models.SaleEvent)
                .where(
                    models.SaleEvent.venue_id == venue_id,
                    models.SaleEvent.status == RECORDED,
                    models.SaleEvent.occurred_at >= since,
                    models.SaleEvent.occurred_at <= until,
                )
                .order_by(models.SaleEvent.occurred_at)
                # One more than the cap, so hitting it is distinguishable from
                # landing on it exactly.
                .limit(limit + 1)
            )
        ).scalars().all()
    )
    if len(events) > limit:
        raise TooManyEvents(venue_id, limit)
    return events


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def profile_from_events(
    *,
    venue: models.Venue,
    events: list[models.SaleEvent],
    since: datetime,
    until: datetime,
) -> RevenueProfile:
    """Aggregate in Python rather than SQL.

    One venue's period is a few hundred to a few thousand rows, and doing it here
    keeps the day bucketing identical on SQLite (dev) and Postgres (prod) -- the
    same reason `merchant_stats` has always done it this way. `events_in_window`
    bounds the set at `MAX_EVENTS_PER_WINDOW` so "a few thousand" stays true.
    """
    period_days = max(1, (until.date() - since.date()).days + 1)

    total = Decimal(0)
    confirmed_total = Decimal(0)
    confirmed_count = 0
    per_day: dict[str, list] = {}
    per_month: dict[str, Decimal] = {}
    per_customer: dict[str, int] = {}
    per_customer_amount: dict[str, Decimal] = {}
    lags: list[float] = []

    for event in events:
        amount = Decimal(event.amount)
        total += amount
        day = event.occurred_at.date().isoformat()
        bucket = per_day.setdefault(day, [Decimal(0), 0, Decimal(0)])
        bucket[0] += amount
        bucket[1] += 1
        month = event.occurred_at.strftime("%Y-%m")
        per_month[month] = per_month.get(month, Decimal(0)) + amount
        if event.source == CONFIRMED:
            confirmed_total += amount
            confirmed_count += 1
            bucket[2] += amount
        if event.customer_id:
            per_customer[event.customer_id] = per_customer.get(event.customer_id, 0) + 1
            per_customer_amount[event.customer_id] = per_customer_amount.get(event.customer_id, Decimal(0)) + amount
        if event.recorded_at and event.occurred_at:
            lags.append(max(0.0, (event.recorded_at - event.occurred_at).total_seconds() / 3600))

    top_share = 0.0
    if per_customer_amount and total > 0:
        top_share = round(float(max(per_customer_amount.values()) / total), 4)

    # Every day in the range, zeros included, so a chart or a statement has no
    # gaps and `active_days` is not confused with "days we have a row for".
    by_day = []
    for i in range(period_days):
        day = (since + timedelta(days=i)).date().isoformat()
        amount, count, confirmed = per_day.get(day, (Decimal(0), 0, Decimal(0)))
        by_day.append(DayBucket(day=day, amount=amount, count=count, confirmed_amount=confirmed))

    currency = next((e.currency for e in events), "XOF")
    return RevenueProfile(
        venue_id=venue.id,
        venue_name=venue.name,
        period_start=since,
        period_end=until,
        currency=currency,
        total=total,
        confirmed_total=confirmed_total,
        declared_total=total - confirmed_total,
        count=len(events),
        confirmed_count=confirmed_count,
        declared_count=len(events) - confirmed_count,
        active_days=sum(1 for b in by_day if b.count > 0),
        period_days=period_days,
        customers=len(per_customer),
        returning_customers=sum(1 for n in per_customer.values() if n > 1),
        top_customer_share=top_share,
        median_recording_lag_hours=round(_median(lags), 2),
        by_day=by_day,
        by_month=per_month,
    )


async def profile(
    db: AsyncSession, *, venue: models.Venue, since: datetime, until: datetime
) -> RevenueProfile:
    events = await events_in_window(db, venue.id, since, until)
    return profile_from_events(venue=venue, events=events, since=since, until=until)
