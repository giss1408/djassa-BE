# Fidelia — Concept Review, Revenue Options and Optimization Proposals

> Independent review of the concept as documented **and as implemented**, produced 2026-09-29.
> Scope reviewed: `docs/` (all concept, business-model, roadmap, inclusion and research notes),
> `backend-api/` (models, APIs, services, tests), `fidelia-App-user`, `fidelia-App-retailer`, `fidelia-Web`.
>
> An ordered, per-step implementation plan for these findings is in
> [Implementation action plan](action_plan_claude_fidelia.md).
>
> This document proposes; it does not decide. Every figure below marked *illustrative* is an
> assumption to test with merchants and partners, not a validated number — consistent with the
> outreach guardrails in [Partners and outreach plan](../business/PARTNERS.md).

## Summary

The strategy documents are strong and the engineering is above the level usually seen pre-pilot.
Three things block monetization today:

1. **No revenue machinery exists in the code.** No subscription, plan, invoice, fee or commission
   concept. The Phase-1 exit gate is "merchants pay or renew" and the system cannot record a payment.
2. **Two parallel, unconnected event streams**, which contradicts the single-primitive thesis of
   [product concept v2](../business/CONCEPT.md) — and the credit export is built on the weaker one.
3. **The consented export is not correctly authorized**, and it is the exact artifact that would be
   shown to a microfinance partner.

A fourth point is strategic rather than technical: the concept's single riskiest assumption —
that customers will pay a maquis by phone instead of cash — is not stress-tested anywhere in `docs/`.

---

## Part 1 — What holds up

Recorded so that the findings below are not read as a verdict on the whole concept.

### Strategy

- **The single-primitive framing is the right one.** One verified transaction, five views on it
  (points, revenue proof, tontine regularity, reliability signal, credit export) is a materially
  better product thesis than five sequential features. See [fidelia-product-concept-v2.md](../business/CONCEPT.md).
- **The regulatory guardrails are unusually disciplined** for a pre-pilot project: never hold funds,
  never lend directly, no opaque scoring, no cash-out before BCEAO clarity, and the *accelerator,
  not gatekeeper* positioning on credit access. See [dkassa-inclusion-financiere.md](../business/CONCEPT.md).
  Most teams discover these constraints after building the wrong thing.
- **The competitive read is sound**: Djamo owns consumer personal finance, so the concept stays out of
  it; tontine digitalization and alternative-data scoring are genuinely under-occupied in Côte d'Ivoire.
- **Revenue ordering is correct in principle** — merchant value before regulated-finance referrals
  ([Business model](../business/BUSINESS-MODEL.md)). The problem is execution, not sequencing.

### Implementation

- **Append-only loyalty ledger.** A balance is always a `SUM`, never a stored total
  (`LoyaltyEntry`, [../backend-api/app/models.py](../../backend-api/app/models.py)). This is the correct
  shape for anything that will later be audited.
- **Idempotency on every money path** — client-generated keys on customer payments and on the
  transaction sync, so a retry after a dropped connection cannot charge twice.
- **Atomic QR claim.** Two phones confirming the same payment request race to a conditional `UPDATE`;
  exactly one wins (`../backend-api/app/api/customer.py`, `pay_venue`).
- **Unguessable pay codes.** 10 characters from a 32-symbol alphabet with `0/O` and `1/I` removed,
  because the code is read aloud across a noisy counter. Rotatable, so a stolen sticker can be voided.
- **The fake payment provider refuses to start in production** (`../backend-api/app/services/mobile_money.py`).
  A fake provider in production would "confirm" payments nobody made.
- **Pending row persisted before the outbound provider call**, so a crash mid-call leaves something to
  reconcile instead of a lost payment.

---

## Part 2 — Findings

### Finding 1 — There is no revenue machinery in the code (blocking)

A search across `backend-api/app/` for subscription, billing, plan, invoice, commission, fee and tier
returns nothing related to money owed to Fidelia. Only identity *verification tiers* match.

Consequences:

- Every unit-economics metric [Business model](../business/BUSINESS-MODEL.md) says to track — MRR, paid conversion,
  renewal rate, gross margin by plan, support cost per active outlet — is currently unmeasurable.
- The Phase-1 exit criterion "merchants pay or renew" ([Roadmap](../business/ROADMAP.md)) cannot be evaluated,
  because no record of a merchant paying can exist.
- The pilot can therefore prove usage but not willingness to pay, which is the more important half.

**Minimum to fix:** a `MerchantSubscription` (venue, plan, period, amount, status, paid_at, provider
reference) and a `DealPlacement` (see revenue line 2). Both are small. Neither requires a partner.

### Finding 2 — Two parallel event streams; the credit export uses the wrong one (blocking)

Two unrelated models both represent "a sale":

| Stream | Tables | Written by | Read by | Evidence quality |
|---|---|---|---|---|
| A | `Transaction` + `Merchant` | retailer app record-sale, `/api/transactions` | `/api/export`, GraphQL | merchant-declared, unverified, no venue link, no loyalty link |
| B | `CustomerPayment` + `Venue` + `LoyaltyEntry` | customer app payment flow | `/api/customer/loyalty`, `/api/merchant/stats` | aggregator-confirmed, linked to venue and points |

They never touch. `Merchant` and `Venue` are separate tables with separate identifiers; nothing joins
a recorded sale to a venue, a payment or a points entry.

This directly contradicts the v2 thesis. "One event, five views" is the correct design — but the code
has two events, and the **credit-history export, on which the whole financial-inclusion revenue line
rests, is built on the unverified stream**. What an IMF would receive today is a list of numbers a
merchant typed in, with no confirmation that any money moved.

**Minimum to fix:** one event table, with a `source` field distinguishing
`mobile_money_confirmed` from `cash_declared`. Keep both kinds of sale — a merchant's cash business is
real and must be recordable — but never blur the evidence classes. See optimizations A and B, which
turn this fix into a commercial asset rather than only a cleanup.

### Finding 3 — The consented export is not correctly authorized (security; fix before any partner demo)

In [../backend-api/app/api/export.py](../../backend-api/app/api/export.py):

- `create_consent` stores `user_id` from the **authenticated caller**, ignoring the payload's `user_id`.
- `export_transactions_csv` then looks for a consent row belonging to **that same caller**.
- `scope` is written but never checked.
- The export returns up to 10,000 rows for the requested `merchant_id`, including every customer's
  `user_id` and amounts.

Net effect: any authenticated user can self-grant consent for any `merchant_id` and download that
merchant's full transaction history, including other people's identifiers. There is no check that the
caller owns the merchant, and no check that the customers whose rows are exported consented to anything.

`tests/test_export.py` currently encodes this as expected behaviour: it grants a consent naming
`"another-user"`, the caller receives the consent instead, and the export succeeds.

This is the single most sensitive endpoint in the system — it is the artifact intended for a regulated
lender, and it touches the data [dkassa-inclusion-financiere.md](../business/CONCEPT.md)
commits to protecting.

**Minimum to fix:** authorize on merchant ownership; require consent from each data subject whose rows
are exported, or aggregate so no individual identifier leaves; enforce `scope`; record who exported
what, when and under which consent; update the test to assert the denial.

### Finding 4 — The riskiest assumption is not in any risk register (strategic)

Every payment-derived revenue line depends on customers **paying a maquis by phone instead of handing
over cash at the counter**. Mobile money is ubiquitous in Côte d'Ivoire for person-to-person transfer;
merchant-presented payment for a 2,000 XOF meal is a different behaviour, and far less established.

`docs/` stress-tests regulation, merchant willingness to pay, identity, fraud and data protection
thoroughly — but never this. Yet it gates lines 1, 3 and 5 below.

Worth stating plainly in the concept: **loyalty points are the incentive that buys this behaviour
change.** That is loyalty's real job in this design, and it should be measured as such — cash-to-digital
conversion per outlet, not only points issued.

### Finding 5 — No real money can move yet (sequencing)

`MOBILE_MONEY_PROVIDER` supports only `fake`; `cinetpay` raises "not implemented yet" and needs a
sandbox key and site ID. `PAYMENT_PROVIDER` has only a sandbox stub returning `pending` and a
`https://sandbox.invalid/` checkout URL.

This is correctly documented as a stub, not hidden — but it means **revenue lines 1, 3 and 5 are all
blocked behind one integration**, which should be reflected in planning.

---

## Part 3 — How to earn money

Ordered by how quickly cash arrives and how few external dependencies are needed. Lines 1–3 do not
require a financial partner. All figures are *illustrative*.

### Line 1 — Payment revenue share with the aggregator *(recommended first line)*

Become a partner/reseller of the licensed aggregator (CinetPay, Hub2) and take a share of the merchant
service charge on each collection.

**Fidelia still never touches funds.** The aggregator settles to the merchant's own wallet and pays
Fidelia a commission on its own fee. This is fully compatible with the non-negotiable constraint in
[dkassa-inclusion-financiere.md](../business/CONCEPT.md).

*Illustrative:* a maquis at 40 sales/day × 2,500 XOF ≈ 3,000,000 XOF/month collected. A 1% share of
turnover ≈ **30,000 XOF per outlet per month** — plausibly more than the same merchant would agree to
pay as a cash subscription (realistically 5,000–10,000 XOF).

Why it is the better first line:

- It scales directly with the master metric (share of real transactions recorded).
- It collects itself; no monthly chase, no churn event.
- It is zero when the merchant gets no value, which makes the pitch honest and the objection small.

Risks to accept: thin per-ticket margin at XOF ticket sizes, and the aggregator can disintermediate
Fidelia once volume exists. **Negotiate the split before building volume, not after.**

### Line 2 — Featured deal placement *(fastest actual cash; nearly built)*

`Deal.is_featured` already exists as an admin-only paid slot, settable only through
`PATCH /api/admin/deals/{id}/feature` — deliberately never self-granted — and the customer app already
renders the sponsored carousel.

Why it converts fastest: local merchants understand paying for *publicité* far more readily than for
SaaS, and it is a one-off sale rather than a monthly commitment.

What is missing: a `DealPlacement` record (deal, period, price, paid_at, status) so a slot **expires**
and can be invoiced. Today a featured deal stays featured indefinitely with no record of who paid.

Guardrail: label sponsored placement visibly, or it erodes the discovery trust that makes the customer
app worth opening at all.

### Line 3 — Merchant subscription, converted at day 30 rather than day 0

Keep it, but stop treating it as the entry offer. Let recording be free, then convert when
`/api/merchant/stats` can show the merchant **their own money** for the first time — that screen is the
sales pitch, and it does not exist until real activity has accumulated.

Suggested paid gates: stats window beyond 7 days, campaigns and messaging, multiple outlets, revenue
statement export. Collect by recurring mobile money.

### Line 4 — Paid reactivation campaigns

SMS/WhatsApp is already the chosen notification channel. Sell message packs with transparent
pass-through cost plus margin, as [Business model](../business/BUSINESS-MODEL.md) already anticipates. Requires the
Phase-2 campaign feature; not built.

### Line 5 — Tontine contribution fee

A small transparent percentage per contribution as an orchestration fee. Module partially exists;
requires the real aggregator (finding 5) and legal sign-off.

### Line 6 — Partner referral commissions: credit, then savings

Correctly identified in `docs/` as the eventual largest line. It is also entirely blocked on findings 2
and 3 plus a signed IMF agreement and regulatory review. **It should not appear in a year-1 forecast.**

### Monetization to refuse

- Charging the **customer** a fee to pay — cash wins instantly.
- Points-to-cash conversion — already correctly forbidden until a licensed partner exists.
- Selling identifiable transaction data.
- Becoming the lender.

---

## Part 4 — Optimization proposals

### A. Collapse to one event table, with an evidence field

Make the verified payment *the* event. Keep merchant-declared cash sales in the **same** stream with a
`source` field (`mobile_money_confirmed` / `cash_declared`), never as a separate table.

An aggregator-confirmed payment and a merchant's typed-in figure are not the same evidence. Keeping
them in one stream with an explicit label is honest and useful; keeping them in two tables, and
exporting the weaker one, will be found by the first partner who audits it.

### B. Turn that distinction into the product: verified revenue share

The share of a merchant's declared turnover that was aggregator-confirmed is exactly what an
underwriter wants, and **nobody in Côte d'Ivoire can currently produce it**. That metric is a stronger
moat than the loyalty program, and it falls out of optimization A for free.

It also gives the merchant a reason to push customers toward digital payment — which is finding 4's
behaviour change, now merchant-driven instead of Fidelia-driven.

### C. Make the export a signed statement, not a CSV dump

No IMF wants 10,000 raw rows. They want a tamper-evident **revenue attestation**: monthly turnover,
regularity, seasonality, customer concentration, verified share, period covered, consent reference,
issuer signature.

A statement is sellable and reviewable. A raw dump is a liability. Do this at the same time as the
finding-3 authorization fix — same endpoint, same work.

### D. Narrow the pilot from six categories to two

`CATEGORIES` currently spans maquis, supérette, pharmacie, mode, beauté and téléphonie. This
contradicts the cluster-density thesis in [Product concept](../business/CONCEPT.md): a customer should
recognize Fidelia across several nearby outlets.

Pilot **maquis + supérette in one or two communes**. Both have high repeat frequency and small tickets,
which is what the recording habit needs.

Pharmacies are an excellent *acquisition* hook (see E) but a poor loyalty target: low visit frequency,
regulated pricing, and prescription data is a privacy problem not worth taking on in a pilot.

### E. Treat pharmacie-de-garde as a distinct strategic asset

It is the only feature with daily urgent pull, there is no official API, and no competitor holds the
data. It can plausibly be sponsored (pharmacy group, health insurer, mutual).

Budget for it honestly: the weekly rotation is entered by hand from the published official list. That
is a real recurring operating cost, currently unaccounted for in any unit-economics figure.

### F. Consider a quartier-level shared rewards pool

Per-venue points are correct for funding fairness — a maquis must not pay for points earned at the
pharmacy next door, as the code comment says. But at pilot scale the customer's experience is
"50 points at one maquis", which feels worthless, and that is the pilot's weakest moment.

A small cluster sharing a pool, funded pro-rata with a settlement table between merchants, fixes it
without breaking the fairness principle.

### G. Cap the points liability

`points_per_100` has no ceiling and `LoyaltyEntry` has no expiry, so a merchant accrues unbounded,
indefinitely-lived liability. Expect this as a sales objection from any merchant who thinks it through.
Add point expiry and a maximum redemption rate per visit or per period.

### H. Instrument the master metric's denominator

[fidelia-product-concept-v2.md](../business/CONCEPT.md) states that the share of a merchant's real
transactions actually recorded is the one number that governs everything. Nothing currently captures
**total real sales**, so the number cannot be computed and the phase gate cannot be enforced.

Add a pilot-only daily merchant self-report ("roughly how many sales today?"). Imperfect, but a rough
denominator beats none.

### I. Resolve the fidelia / dkassa naming before institutional outreach

Both names are live across `docs/`, sometimes in the same sentence. Settle it and check trademark
availability before any partner meeting — this is already an open item in [concept.md](../business/CONCEPT.md).

---

## Part 5 — Suggested sequencing

The critical path is short and the order matters:

| # | Work | Unblocks | Needs a partner? |
|---|---|---|---|
| 1 | `DealPlacement` + featured-slot billing | Revenue line 2 — first real cash | No |
| 2 | Fix export authorization (finding 3) | Any partner demo; removes a data-protection exposure | No |
| 3 | Merge the event streams with a `source` field (finding 2, optimization A) | Optimizations B and C; the entire credit thesis | No |
| 4 | Signed revenue statement (optimization C) | Revenue line 6 conversation | No, but shaped with one |
| 5 | CinetPay integration (finding 5) | Revenue lines 1, 3 and 5 | Aggregator |
| 6 | `MerchantSubscription` + billing records (finding 1) | Revenue line 3; the Phase-1 exit gate | No |

Items 1–3 are each small, require no external dependency, and can start immediately. Item 5 is the
long-pole external dependency and should be requested in parallel with item 1, not after it.

---

## Open questions for the team

1. Is the aggregator commission split (line 1) negotiable at pilot volume, or only after traction?
   The answer changes which revenue line goes first.
2. Has any merchant been asked whether they would accept revenue share instead of a subscription?
3. What is the actual observed rate of merchant-presented mobile-money payment in the target communes
   (finding 4)? If it is very low, loyalty's role and the pilot's success metric both need restating.
4. Who owns the weekly pharmacie-de-garde data entry, and what does it cost per month (optimization E)?

---

Related documents:

- [Implementation action plan](action_plan_claude_fidelia.md) — how to execute the findings above
- [Concept (FR)](../business/CONCEPT.md)
- [Product concept](../business/CONCEPT.md)
- [Product concept v2 — the event as core primitive](../business/CONCEPT.md)
- [Business model](../business/BUSINESS-MODEL.md)
- [Financial inclusion scope (FR)](../business/CONCEPT.md)
- [Product roadmap](../business/ROADMAP.md)
- [Partners and outreach plan](../business/PARTNERS.md)
