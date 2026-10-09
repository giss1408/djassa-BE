# Fidelia — Business Model

## Thesis

**Merchant software first, financial infrastructure second.** The merchant subscription funds the product. Partner revenue arrives only after reliable usage, traceable consent, clean reconciliation and a confirmed regulatory perimeter.

Revenue is layered so that **the first revenue never depends on credit approval or on Fidelia holding funds**. Over time, distribution commissions from licensed partners are expected to become the largest line. They are not assumed in any plan until a partner agreement exists.

The go-to-market unit is not a country but a **merchant cluster**: one dense corridor in Abidjan, reached through an association, distributor, payment partner or MFI. A cluster lowers acquisition and support cost, and lets customers recognise Fidelia across nearby outlets.

## Customers and value exchange

| Party | Who | What they get | What they give |
|---|---|---|---|
| **Merchants** (paying customer) | Repeat-purchase outlets: pharmacies, maquis and restaurants, neighbourhood groceries, salons, service shops | Loyalty and deals without building software; daily totals and repeat-customer visibility; a revenue history they own; optional access to partner finance; paid visibility for a product, service or special offer | Monthly subscription; one-off sponsored placement; optional campaigns |
| **Customers** (free) | Residents of the pilot corridor | A daily-use app (food, on-duty pharmacies, deals, payment); points and rewards; a view of their own activity; access to tontines and savings through partners later | Usage, and payment-confirmed events that strengthen merchant histories |
| **Financial partners** | MFIs, banks, guarantee schemes | Distribution into small merchants and communities; consented, structured histories; lower onboarding friction | Referral and distribution commissions |
| **Payment partners** | Aggregators, mobile-money operators | Repeat merchant QR-payment volume on their rails | Integration, settlement; possibly revenue share where licensing permits |
| **Institutions** | APIF, guarantee programmes, funders | A private execution channel for inclusion goals, with measurable, gender-disaggregated outcomes | Introductions, programme access, co-funded pilots |

Avoid starting with businesses whose purchase frequency is too low to prove retention value.

## Revenue streams, in order

| # | Stream | Detail | When |
|---|---|---|---|
| 01 | **Merchant subscription** | Monthly per outlet, tiered by activity, paid in mobile money. Primary MVP revenue. | MVP |
| 02 | **Sponsored deals and campaigns** | Basic deals remain free. A merchant can buy a one-off, fixed-price, time-limited placement to promote a product, dish, service or special price in the customer app, shown to people browsing the relevant commune/category. Placements are visibly labelled sponsored, capped per commune/category, and admin-assisted during the pilot. The fee buys placement, not guaranteed sales; price and demand must be tested. SMS/WhatsApp campaigns are optional and their messaging costs are passed through transparently. | MVP |
| 03 | **Multi-outlet and network contracts** | Merchant networks, pharmacy groups, associations; priced separately from single outlets. | After proof |
| 04 | **Payment orchestration** *(minor)* | An aggregator revenue share on payments made through the Fidelia route only, where the licensed provider permits it. **Never priced above what the merchant pays on their existing wallet today (~1% on Wave).** This is not a core stream, because Fidelia builds on the merchant's existing wallet (see [CONCEPT.md § 3](CONCEPT.md#3-the-idea-one-habit-five-uses)). | After proof |
| 05 | **Consented partner commissions** | Paid by a licensed partner for a qualified, consented referral: credit (working capital, stock, revenue advance), savings accounts opened and funded, tontine processing fees. Fidelia never touches the funds, only the distribution commission. Moniepoint (36% transaction lift after loans) and Kopo Kopo (42%) show this is where merchant platforms create the most value, as long as responsible-lending safeguards are in place (see below). | After partnership |
| 06 | **Institutional services** | Reporting, reconciliation and aggregated, anonymised, consented insight for institutions. Never casual sale of personal data. | After partnership |

## Additional revenue experiments (not in the forecast)

These are options to test after the core merchant pilot; none is committed revenue. Keep the basic merchant and customer services useful without requiring these purchases.

| Option | Who pays and what they buy | Timing and conditions |
|---|---|---|
| **Done-for-you offer creation** | A merchant pays a one-off service fee for Fidelia to prepare the photo, copy, local-language version, and schedule for a sponsored offer. Ordinary deal publishing remains free. | Can be tested manually during the pilot. Price from actual staff time and merchant willingness to pay; do not add a fee that costs more than the promotion itself without clear value. |
| **Brand- or distributor-funded local campaigns** | A consumer-goods brand or distributor pays a flat campaign fee to promote a product or funded offer at participating merchants. The merchant approves the offer; any discount/reward funding is explicit. | After a corridor has enough active merchants and customer attention to offer reliable placement. Label advertising clearly; share no customer-level data and do not let sponsors influence pharmacy-duty or safety information. |
| **Association or chain setup contracts** | A merchant association, pharmacy group, or small chain pays a one-time setup/training fee plus an agreed per-outlet service fee for onboarding, configuration, and group reporting. | After one corridor proves onboarding and support costs. Keep terms transparent and do not imply access to credit is included. |
| **Opt-in supplier introductions** | A distributor or business-service provider pays a disclosed fee for a merchant-requested introduction or qualified inquiry (for example, a wholesaler quote request). Fidelia does not take orders or handle the purchase payment. | Later, after merchants trust the service and a written partner agreement exists. The merchant chooses whether to share contact details; no sales history is passed to suppliers. |
| **Layaway ("payer en plusieurs fois")** | Nobody pays Fidelia directly at first: the merchant gets cash up front and a sale they are sure of, the customer gets a disciplined way to buy an expensive good. It can later be a Growth-plan feature. See [Layaway test](#layaway-test). | Pilot test after the Phase 1 gate, with 2–3 merchants whose goods suit it (electronics, appliances, furniture, school supplies). Switched on per shop by an admin. |

Prioritize the first three before supplier referrals. Track paid conversion, delivery cost, renewal/repeat booking, and merchant benefit separately for every experiment. Reject any offer that needs hidden advertising, sale of identifiable data, a new regulated role, or merchant payments routed through Fidelia.

### Layaway test

The customer pays for one named good in several installments; the merchant keeps the money and hands the good over when the price is reached. Fidelia records the plan and every installment. **It is not credit and is never called credit**: the customer pays first and nobody lends anything.

Why it fits: no new habit (an installment is recorded like a sale), cash up front for the merchant, and each completed plan is proof of saving discipline that can later feed the reliability indicator (Phase 4).

Guardrails, enforced by the API (`app/api/layaway.py`):

- One named good, at a price fixed when the plan opens, with an end date (at most `LAYAWAY_MAX_DAYS`, default 183) and a price cap (`LAYAWAY_MAX_PRICE`, default XOF 1,000,000). An open-ended refundable balance would start to look like taking deposits from the public.
- The merchant reads the terms to the customer and ticks their agreement before anything is recorded; the plan stores the terms version.
- The money goes to the merchant, in cash or to their own wallet, **never through Fidelia**. No interest, no fee, no penalty.
- The good becomes one sale, for its full price, only on handover. A cancelled plan leaves no sale behind, and records what the merchant says they refunded.
- The customer sees the plan and each installment in the customer app.

Risk to watch: the customer carries the risk of the merchant failing to deliver, and Fidelia's name is on the record. Choose pilot merchants carefully, review disputes weekly, and get legal advice on Loi 2016-412 (consumer law: down payments and earnest money) before going beyond the pilot. The safer long-term form is the same feature with the money held by a licensed partner, i.e. the goal-based savings of Phase 5.

**Continue only if:** completion rate (delivered ÷ ended plans) ≥ 70%, disputes under 5% of plans, and the participating merchants say it brings new customers. KPIs in [KPI.md § 3.4](KPI.md#34-layaway-test).

**Referral revenue is not the model's first assumption.** It depends on a partner agreement, regulatory review, user consent and measurable financial outcomes. Commissions must never create pressure on users or condition access to basic service. We earn the value of the credit generated without carrying its risk. Fidelia does not lend.

Customers pay nothing for basic use. Who bears the aggregator fee on a Fidelia-route payment (merchant, customer, or split) is an open pricing question for the pilot and must be displayed before payment.

**Responsible merchant credit.** Kopo Kopo's merchants re-borrowed after a median of 3 days and nearly always took the maximum offered. Partner-credit flows through Fidelia must therefore: show the cost of an advance against its expected return; let the merchant choose a lower amount; prefer repayment as a share of daily takings over fixed instalments; and flag continuous re-borrowing. These rules protect users and they protect Fidelia's reputation with regulators.

## Why a merchant pays: the value equation

The subscription must be small compared with what loyalty brings in. It also has to cover Fidelia's own biggest variable cost, which is customer notifications. The figures below are **illustrative assumptions to test in the pilot**, built from the averages in [MARKET.md § 9](MARKET.md#9-evidence-for-the-fidelia-model).

| | Small maquis | Neighbourhood pharmacy |
|---|---|---|
| Tickets per day × average basket | 40 × 4,000 F | 60 × 8,000 F |
| Monthly takings (26 days) | ~4.2M F | ~12.5M F |
| Of which via mobile money (maquis ~60%, pharmacy ~55%) | ~2.5M F | ~6.9M F |
| Loyalty target: extra takings from repeat visits | +5% → ~210,000 F | +3% → ~375,000 F |
| Extra gross profit (assumed margin 35% / 22%) | **~73,000 F** | **~83,000 F** |
| Subscription hypothesis | 5,000 F | 10,000 F |
| Merchant return on subscription | ~14× | ~8× |
| **Cost if payments were rerouted through an aggregator (+2 pts on wallet takings)** | **−50,000 F** | **−140,000 F** |

Two conclusions:

1. A small subscription is easy to justify **if** loyalty measurably brings customers back. The merchant must see that number every week.
2. Rerouting payments through a more expensive rail would wipe out most or all of the gain. That is why Fidelia builds on the merchant's existing wallet QR (Wave first, other operators and the interoperable PI-SPI QR next) rather than replacing it.

**Notification cost is the hidden risk.** If every visit triggered a paid SMS, a busy maquis with ~600 identified visits a month could cost more in messages than it pays in subscription. Rules: confirm points in the customer app (free push) when the customer has it; otherwise send a batched weekly SMS or WhatsApp summary, not one message per visit; sell campaign messages as a pass-through; and measure the real cost per active outlet in the pilot.

## Pricing experiment

Pricing is tested with merchants, not fixed. The first experiment, informed by Bumpa's capped free tier and the value equation above:

| Plan | Hypothesis to test | Includes |
|---|---|---|
| **Free** | 0 F, capped (e.g. 50 loyalty customers) | Sales recording, basic loyalty, daily totals. Builds the habit and the history. |
| **Starter** | ~5,000 F / month / outlet | Unlimited loyalty customers, automatic capture of wallet payments, weekly "customers who came back" report. |
| **Growth** | ~10,000–15,000 F / month / outlet | Lapsed-customer win-back, deals, campaign tools, revenue-history export. |
| **Network** | Negotiated | Multiple outlets, association or pharmacy-group dashboards, partner-finance workflows. |

Rules: local currency (XOF), paid in mobile money; state whether messaging, payment and partner fees are included; **a paid pilot, not a permanently free product** (the free tier is a funnel with a cap, not the business); a short trial only once the merchant has onboarded and recorded real activity; network contracts priced separately; financial referral revenue kept outside the subscription; never sell credit access as part of a plan.

**Sponsored-deal pilot offer.** Keep ordinary deal listings free, then offer a fixed-fee placement for a defined time window in the customer app. The merchant supplies the offer and commune/category; Fidelia checks it, records the fee and dates, and labels it sponsored. Pilot requests and sales are handled by the team, not self-service checkout. Test 7-day placement prices of **XOF 1,000, 2,000, and 3,000** with comparable merchants; these are starting hypotheses, not researched market rates or a published tariff. Track paid bookings and direct delivery costs before forecasting this revenue. Do not promise a number of views, visits or sales, and never let payment affect official pharmacy-duty or other safety-critical information.

**Acquisition through resellers.** Commission associations, distributors and field agents on the subscriptions they bring in (Bumpa pays partners 20%). This is cheaper than direct sales and fits the cluster strategy.

## Unit economics

Per pilot merchant: monthly recurring revenue · acquisition cost and onboarding time · active customers per outlet · **% of real sales recorded** (master metric) · transactions per active merchant · retention at 30/60/90 days · messaging and payment cost per transaction · **notification cost per active outlet** · **repeat-visit rate of identified customers (before and after joining)** · reward cost as a share of member sales · free-to-paid conversion · support cost per merchant · gross margin by plan · data consumed per active user.

Per partner-finance experiment, tracked separately: qualified referrals · applications started and completed · approval and repayment outcomes (where legally shareable) · commission revenue · consent and withdrawal rates · **women's share of each outcome**.

## Decision gates

**Pilot gate.** Scale only when the pilot shows consistent transaction capture, repeat customer usage, merchants paying or renewing, a measurable operational advantage for at least one financial or payment partner, and no unresolved critical privacy, authorisation, reconciliation or regulatory issue.

**Unit-economics gate.** No geographic expansion until one corridor shows:

- Acquisition cost below twelve months of expected gross profit.
- Three consecutive months of retention or renewal.
- Support and messaging costs known per active outlet.
- A repeat-purchase improvement merchants understand.
- A path to positive contribution margin **without assuming future credit commissions**.

## Long-term platform option

The event stream and progressive verification could found a federated identity trust service (see [CONCEPT.md § 7](CONCEPT.md#7-identity-inherit-trust-do-not-rebuild-it)). The business would be consent orchestration, verification workflows, assurance-level normalisation and audit for licensed institutions, not selling identity data. Possible pricing: integration fees, per-verification fees, enterprise subscriptions. It stays downstream of the merchant product and needs governance, liability allocation and regulatory legitimacy first.

## Financial and regulatory boundaries

Fidelia must not hold deposits or savings balances (not even in a transit account), lend without authorisation, guarantee credit approval, share identifiable data without a defined purpose and valid consent, or charge hidden fees. Before any payment, savings, scoring or credit feature: legal advice, a confirmed licensed-partner role, and **a technical audit of the funds flow before launch, not after**.

Identity verification is a cost decision too: keep Tier 0 onboarding cheap and fast; trigger biometric or national-ID checks only when the fraud, financial or underwriting benefit justifies the cost and the user has a clear reason to complete it.

## Related documents

[CONCEPT.md](CONCEPT.md) · [MARKET.md](MARKET.md) · [ROADMAP.md](ROADMAP.md) · [PARTNERS.md](PARTNERS.md)
