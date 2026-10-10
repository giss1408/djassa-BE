"""What each plan allows, in one place.

Deliberately *not* gated, on any plan: recording a sale, issuing and redeeming
loyalty points, publishing a bon plan. The share of a merchant's real
transactions that reach Fidelia is the metric every downstream feature depends on
-- loyalty perception, the reliability signal, the revenue history shown to a
lender -- so putting the recording habit behind a paywall would trade the whole
financing case for a few thousand XOF a month
(docs/fidelia-product-concept-v2.md, docs/optimization_claude_fidelia.md).

What is gated is the reporting and reach a paying merchant gets on top.
"""

from __future__ import annotations

from enum import Enum

# Free days of history on the unpaid plan. Long enough to prove the product
# works, short enough that a merchant who wants last month has a reason to pay.
STARTER_STATS_DAYS = 7

# Plans that count as paying. `trialing` is included on purpose: a trial exists
# to show the paid experience, and a trial that behaves like the free plan
# demonstrates nothing.
PAYING_STATUSES = frozenset({"trialing", "active", "past_due"})


class Feature(str, Enum):
    LONG_STATS = "long_stats"  # a reporting window beyond STARTER_STATS_DAYS
    CAMPAIGNS = "campaigns"  # paid SMS/WhatsApp reactivation
    MULTI_OUTLET = "multi_outlet"
    REVENUE_STATEMENT = "revenue_statement"  # the signed export for a lender


_PLANS: dict[str, frozenset[Feature]] = {
    "starter": frozenset(),
    # The free pilot (docs/business/CONCEPT.md § 12): everything a pilot
    # merchant needs is free, including the signed statement a partner MFI
    # reads (docs/business/PROPOSITION-PILOTE-FINELLE.fr.md). Never billed:
    # the admin endpoint refuses an amount on this plan. Paid SMS/WhatsApp
    # campaigns stay out, as the pilot does not use them.
    "pilot": frozenset({Feature.LONG_STATS, Feature.REVENUE_STATEMENT}),
    "growth": frozenset({Feature.LONG_STATS, Feature.CAMPAIGNS}),
    "network": frozenset(
        {Feature.LONG_STATS, Feature.CAMPAIGNS, Feature.MULTI_OUTLET, Feature.REVENUE_STATEMENT}
    ),
}

DEFAULT_PLAN = "starter"
PILOT_PLAN = "pilot"
PLAN_NAMES = tuple(_PLANS)


def effective_plan(subscription) -> str:
    """The plan a venue is really on.

    No subscription row, or one that is cancelled, reads as starter: a pilot
    merchant is signed up long before anyone bills them, and losing access to
    their own recording because billing lapsed is exactly the failure this
    module exists to avoid.
    """
    if subscription is None or subscription.status not in PAYING_STATUSES:
        return DEFAULT_PLAN
    return subscription.plan if subscription.plan in _PLANS else DEFAULT_PLAN


def plan_allows(subscription, feature: Feature) -> bool:
    return feature in _PLANS[effective_plan(subscription)]


def max_stats_days(subscription) -> int | None:
    """Days of history the venue may read. None = no limit."""
    return None if plan_allows(subscription, Feature.LONG_STATS) else STARTER_STATS_DAYS
