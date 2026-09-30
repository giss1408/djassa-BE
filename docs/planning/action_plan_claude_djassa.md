# Djassa — Implementation Action Plan

> Companion to [Concept review and optimization proposals](optimization_claude_djassa.md).
> The review states *what* is wrong and *what* to monetize. This plan states *in which order to do it*,
> *which files change*, and *how each step is proven done*. Produced 2026-09-29.
>
> Effort figures are indicative sizing for one developer, not commitments.
> Steps W4-* are concept and commercial work, not code, and can run in parallel with everything else.

## How to use this plan

Four workstreams, deliberately ordered so that **money starts arriving before the expensive work begins**
and **nothing is shown to a partner before it is correct**:

| Workstream | Purpose | External dependency |
|---|---|---|
| **W1 — Revenue machinery** | Make it possible to be paid, and to record having been paid | None |
| **W2 — Trust and correctness** | Fix what must not be demonstrated in its current state | None |
| **W3 — One event stream** | Restore the single-primitive thesis; make the credit asset real | None |
| **W4 — Concept and pilot design** | Sharpen positioning, narrow the pilot, instrument the master metric | Merchants |

Rule of sequencing: **W1 and W2 before W3, W3 before any partner conversation, the aggregator request
opened on day one** because it is the only long-pole external dependency.

## Standing rules for every step

Carried over from [dkassa-inclusion-financiere.md](../business/CONCEPT.md) and
[djassa-product-concept-v2.md](../business/CONCEPT.md). A step that breaks one of these is wrong
even if it ships:

1. **Djassa never holds funds** — not even in transit, not even "technically". Commission is paid *to*
   Djassa by a licensed party; customer money goes customer wallet → merchant wallet.
2. **No new merchant habit.** Every feature is a view on the recorded transaction. If a step asks the
   merchant to do a second thing daily, it needs an explicit justification.
3. **Evidence classes never blur.** An aggregator-confirmed payment and a merchant-typed figure are
   labelled differently, forever.
4. **Every schema change ships with a migration and a test.** Migration head is currently `0010_deals`.
5. **Nothing identifiable leaves the system without an authorization check and an audit row.**

---

# Phase 1 — Cash and correctness (no external dependency)

> **Status: implemented 2026-09-29.** W1-1, W1-2 and W2-1 are built, tested and
> verified against Postgres (migrations `0011`–`0013` roll forward and back).
> Deltas from the plan as written are noted per step below.
> **Phase 2 (W3-1 – W3-3) is also implemented** — see
> [Phase 2 implementation notes](#phase-2-implementation-notes). Phase 3 is not started.

## W1-1 — Sell the featured deal slot — **DONE**

The slot already exists and is already admin-only. What is missing is the commercial record, so a
placement expires and can be invoiced.

**Why first:** local merchants buy *publicité* far more readily than SaaS, it is a one-off sale rather
than a monthly commitment, and it needs no payment integration — the first placements can be collected
by direct mobile-money transfer and recorded by an admin.

**Schema** — new migration `0011_deal_placements`:

```
deal_placements
  id, deal_id → deals.id, venue_id → venues.id
  starts_at, ends_at                     -- the slot window
  price, currency                        -- XOF
  status                                 -- reserved | active | expired | cancelled
  paid_at, payment_reference              -- nullable: how the merchant settled
  created_by, created_at                  -- which admin sold it
```

**Code**

- `app/models.py` — add `DealPlacement`.
- `app/api/deals.py` — replace the boolean flip in `feature_deal` with placement creation. Keep
  `Deal.is_featured` as the read-side flag so the app needs no change, but **derive** it from an active
  placement rather than setting it by hand.
- `app/api/deals.py::list_deals` — a deal is featured only while a placement is `active` and within its
  window. This is what makes the slot expire on its own.
- `app/tasks.py` or `celery_tasks.py` — periodic job to expire placements past `ends_at`.
- New `GET /api/admin/placements` — what is sold, running and expiring, so the slot can be resold.

**Tests** (`tests/test_deals.py`, extend)

- A placement outside its window does not appear in `featured=true`.
- A merchant cannot create a placement (403) — only an admin.
- An expired placement flips the deal out of the carousel.
- Two overlapping placements for the same window are refused, or the inventory limit is enforced.

**Done when:** an admin can sell a dated slot, it appears in the carousel only for its window, it
expires unattended, and `GET /api/admin/placements` shows what is owed.

**Also required (W4):** decide slot inventory (how many featured at once — scarcity is the product) and
a price list. Recommend: 2 slots per commune per category, priced weekly.

## W1-2 — Subscription and billing records — **DONE**

Without this the Phase-1 exit gate "merchants pay or renew" ([Roadmap](../business/ROADMAP.md)) cannot be evaluated.
Build the *record* now; automated collection waits for W3-4 (aggregator).

**Schema** — migration `0012_merchant_billing`:

```
merchant_subscriptions
  id, venue_id → venues.id
  plan                                   -- starter | growth | network
  status                                 -- trialing | active | past_due | cancelled
  amount, currency, period               -- monthly
  current_period_start, current_period_end
  started_at, cancelled_at, created_at

billing_events
  id, subscription_id → merchant_subscriptions.id
  kind                                   -- invoice_due | paid | failed | refunded
  amount, currency
  payment_reference                      -- mobile-money reference, nullable
  occurred_at, recorded_by
```

**Code**

- `app/models.py` — both tables.
- New `app/api/billing.py` — merchant reads own subscription; admin records a manual payment
  (pilot reality: the first payments will be collected by hand).
- `app/core/entitlements.py` — one function, `plan_allows(venue, feature)`. Gate the *paid* features
  only: stats window beyond 7 days, campaigns, multi-outlet, revenue-statement export.
- `app/api/payment_requests.py::merchant_stats` — apply the stats-window gate. **Deliberately leave
  recording and loyalty ungated:** the recording habit must never be behind a paywall, or the master
  metric and every downstream asset die with it.

**Tests** — new `tests/test_billing.py`

- A trialing venue can record sales and see 7 days of stats.
- Requesting a 90-day window on the starter plan is refused with a clear message.
- Recording a payment moves `past_due` → `active` and appends a `billing_events` row.
- A merchant cannot alter their own plan (403).

**Done when:** MRR, paid conversion and renewal are answerable from the database.

## W2-1 — Fix the export authorization — **DONE**

Finding 3 in the review: today any authenticated user can self-grant consent for any `merchant_id` and
download that merchant's full history including other customers' identifiers.

**Code** — `app/api/export.py`, rewritten around three changes:

1. **Ownership.** Authorize on the merchant/venue the caller actually owns. Reuse the existing pattern
   `_my_venue()` from `app/api/payment_requests.py` — it is already the convention for
   "this merchant, from the token, never from the URL". Remove `merchant_id` from the path.
2. **Consent that means something.** `create_consent` must stop overwriting `user_id` with the caller.
   A merchant exporting *their own revenue* needs no customer consent — but then the export must carry
   **no customer identifiers**. Exporting per-customer rows requires a consent row per data subject.
   Default the endpoint to the aggregate form.
3. **Scope enforced, export audited.** Check `Consent.scope`. Append an `export_audit` row
   (who, what, when, which consent, row count) on every call — a partner will ask for this, and it is
   the difference between a consented export and an undocumented data transfer.

**Schema** — migration `0013_export_audit` (audit table; `consents` needs no change).

**Tests** — rewrite `tests/test_export.py`, which currently asserts the bug as expected behaviour:

- Self-granting consent for a merchant you do not own → 403 (this test replaces the existing one).
- The default export contains no customer identifiers.
- A per-customer export without that customer's consent → 403.
- A successful export writes exactly one audit row.
- Wrong `scope` → 403.

**Done when:** no path exists from an arbitrary account to another merchant's customer-level data, and
every export is attributable.

> Note: `_DEMO_USERS` in `app/api/auth.py` is three hardcoded logins. That is fine for a skeleton but is
> a hard blocker for a real pilot — real merchant accounts are needed before W3-4. Track it as its own
> item; it is out of scope for this step.

---

## Phase 1 implementation notes

What was built, and where it departed from the plan above.

### Delivered

| Step | Migration | New endpoints | Tests |
|---|---|---|---|
| W1-1 | `0011_deal_placements` | `POST /api/admin/deals/{id}/placements`, `GET /api/admin/placements`, `POST /api/admin/placements/{id}/paid`, `POST /api/admin/placements/{id}/cancel` | `tests/test_deal_placements.py` (7) |
| W1-2 | `0012_merchant_billing` | `GET /api/merchant/subscription`, `GET /api/merchant/billing/events`, `PUT /api/admin/venues/{id}/subscription`, `POST .../payments`, `POST .../unpaid`, `GET /api/admin/subscriptions`, `GET /api/admin/revenue` | `tests/test_billing.py` (8) |
| W2-1 | `0013_export_audit` | `GET /api/export/merchant/revenue.csv`, `GET /api/export/merchant/customers.csv`, `DELETE /api/consents/{id}`, `GET /api/admin/export-audits` | `tests/test_export.py` (7, rewritten) |

### Decisions taken during implementation

- **`Deal.is_featured` is now derived, not set.** The apps still read the boolean,
  so no client changed, but `list_deals` filters on a *live placement* rather than
  trusting the flag. A campaign therefore leaves the carousel the moment its window
  closes, even if the expiry sweep has not run — reads are defended, the sweep is
  only housekeeping.
- **Slot inventory is capped at 2 per commune+category** (`FEATURED_SLOTS_PER_SEGMENT`).
  This was left open in the plan as a commercial decision; a default was needed to
  build the conflict check, and W4-4 should confirm the number.
- **Seeded sample deals now get sample placements.** Without them the demo data
  contradicted its own rule: featured deals whose flag the first sweep would clear.
- **Unpaid does not un-feature, and past_due does not downgrade.** Chasing payment
  is a commercial matter; cutting a merchant off from their own history over a late
  transfer would damage the recording habit the whole thesis rests on.
- **`trialing` counts as paying for entitlements, but not for MRR.** A trial that
  behaves like the free plan demonstrates nothing; a trial counted as revenue
  overstates the one number the scale decision rests on.
- **A late payment rolls from the period end, not from today**, so lateness does
  not buy a free extension.
- **The export was split rather than patched.** `revenue.csv` is the default and
  names no customer — it answers the underwriting question (regularity, volume,
  repeat counts) without a single identifier leaving. `customers.csv` requires a
  consent *per data subject* and omits non-consenting customers entirely. The old
  `GET /api/export/merchant/{merchant_id}` path is gone; nothing called it.
- **`create_consent` now validates the merchant exists.** Found by running the
  live server against Postgres: the foreign key turned an unknown merchant into a
  500. SQLite had not been enforcing foreign keys at all, so
  `tests/conftest.py` now sets `PRAGMA foreign_keys=ON` — which immediately caught
  two of the new tests relying on a merchant id that did not exist.

### Not done in Phase 1

- **Recurring collection** (W1-3). Payments are recorded by an admin, which is what
  the pilot needs; automated collection belongs with the aggregator (W3-4).
- **Campaigns, multi-outlet and the revenue statement** are defined as plan
  entitlements but the features themselves do not exist yet. `Feature.REVENUE_STATEMENT`
  is the gate W3-3 will use.
- **Phase 2 was untouched at the time of writing**, so the two event streams and
  the concept-integrity problem in finding 2 remained open. The export read the
  *confirmed* payment stream rather than the unverified one, which narrowed the
  exposure without closing the finding. **Closed in Phase 2 by W3-1** (migration
  `0014_sale_events`).

---

# Phase 2 — One event stream (the concept-integrity work)

> **Status: implemented 2026-09-29.** All three steps are built and verified against
> Postgres. See [Phase 2 implementation notes](#phase-2-implementation-notes) for what
> departed from the plan below.

Start after W2-1 is merged. This is the step that makes the credit thesis real instead of nominal.

## W3-1 — Merge the two event streams — **DONE**

Today `Transaction`/`Merchant` (merchant-declared, what the retailer app posts and what `/api/export`
reads) and `CustomerPayment`/`Venue`/`LoyaltyEntry` (aggregator-confirmed, loyalty-linked) never touch.
The credit export is built on the unverified one.

**Target shape** — one stream, one evidence field:

```
sale_events
  id, venue_id → venues.id
  source            -- mobile_money_confirmed | cash_declared
  amount, currency
  occurred_at                             -- when the sale happened
  recorded_at                             -- when it reached us (offline gap is itself a signal)
  customer_id                             -- nullable: a cash sale may be anonymous
  payment_id → customer_payments.id       -- nullable, set for confirmed sales
  loyalty_entry_id → loyalty_entries.id   -- nullable
  idempotency_key                         -- unique
```

`CustomerPayment` stays as the payment-mechanics record; `sale_events` becomes the single stream every
view reads. Keep the append-only discipline already used by `LoyaltyEntry`.

**Migration** `0014_sale_events`, in this order — and this is the part to get right:

1. Create `sale_events`.
2. Backfill from `customer_payments` where `status = 'succeeded'` → `source = 'mobile_money_confirmed'`.
3. Backfill from `transactions` → `source = 'cash_declared'`, resolving venue via
   `Venue.merchant_id` (the column already exists and is the intended bridge).
4. **Unresolvable rows are the real work.** The retailer app posts a hardcoded
   `merchant_id = 1` (`RecordSaleScreen.demoMerchantId`), and `/api/transactions` *creates a merchant
   row on demand* for unknown ids. So existing declared sales may not map to any real venue. Do not
   invent a mapping: migrate them to a quarantine state, count them, and report the count. Pilot data
   integrity matters more than a clean-looking migration.

**Code**

- `app/models.py` — `SaleEvent`; keep `Transaction` temporarily for rollback safety, mark deprecated.
- `app/api/customer.py::settle_payment` — on transition to `succeeded`, write the `sale_event` in the
  same transaction that grants points. One event, both views, atomically.
- **New `POST /api/merchant/sales`** — venue derived from the token via `_my_venue`, writing
  `source = 'cash_declared'`. This replaces client-supplied `merchant_id` entirely.
- `app/api/export.py`, `app/api/payment_requests.py::merchant_stats`, `app/graphql_api.py` — read
  `sale_events`.

**Retailer app** (`djassa-App-retailer`)

- `lib/core/model/sale.dart` — drop `merchant_id` from `toApiJson()`/`toSyncOperationJson()`; the server
  derives it. Keep `idempotency_key`.
- `lib/features/record_sale_screen.dart` — delete `demoMerchantId`.
- `lib/core/data/sync_service.dart` — point at the new endpoint. **Preserve the existing idempotency
  and duplicate-detection behaviour exactly**; it is correct today and is the thing most likely to break.
- `test/sync_service_test.dart` — update, keeping the duplicate-protection assertions.

**Tests** — new `tests/test_sale_events.py`

- A succeeded payment writes exactly one event with `source = 'mobile_money_confirmed'`.
- A failed payment writes none.
- A declared sale writes `cash_declared` and cannot set its own venue.
- Replaying an idempotency key creates no second event.
- Stats and export totals match the sum of events for the window.
- Migration test: a `transactions` row with an unresolvable merchant lands in quarantine, not silently
  attached to a venue.

**Done when:** one table answers "what did this venue sell", every row is labelled by evidence class,
and no client can assert which venue a sale belongs to.

## W3-2 — Verified revenue share — **DONE**

The share of a venue's turnover that was aggregator-confirmed. Falls out of W3-1 almost free, and it is
the metric **no competitor in Côte d'Ivoire can currently produce** (review optimization B).

- `app/services/revenue.py` — compute per venue per period: total declared, total confirmed, verified
  share, regularity (active days / days in period), customer concentration.
- Surface in `merchant_stats` so the merchant sees their own figure — which gives *them* the incentive
  to push customers to digital payment. That is the behaviour change in finding 4, merchant-driven.

**Done when:** a merchant can see their verified share and it moves when payment mix changes.

## W3-3 — The revenue statement, replacing the CSV dump — **DONE**

No IMF wants 10,000 raw rows; they want a reviewable attestation (review optimization C).

- `app/services/statement.py` — period, monthly turnover, verified share, regularity, seasonality,
  customer concentration, consent reference, issuer signature, schema version.
- `GET /api/merchant/statement?from=&to=` — merchant's own, gated to a paid plan (W1-2).
- Sign it (detached signature over a canonical serialization) so a partner can verify it was not edited
  after issue. Without that, it is a spreadsheet with a logo.
- Audited via the same `export_audit` table from W2-1.

**Tests** — statement totals reconcile with `sale_events`; a tampered payload fails verification;
an unpaid plan is refused; every issue writes an audit row.

**Done when:** the artifact shown to an IMF is a signed statement, and its numbers reconcile with the
event stream by construction.

---

## Phase 2 implementation notes

What was built, and where it departed from the plan above.

### Delivered

| Step | Migration | New endpoints | Tests |
|---|---|---|---|
| W3-1 | `0014_sale_events` | `POST /api/merchant/sales`, `POST /api/merchant/sales/sync`, `GET /api/admin/sale-events/quarantined`, GraphQL `mySales` | `tests/test_sale_events.py` (12), `tests/test_sale_events_migration.py` (6) |
| W3-2 | — (falls out of W3-1) | extends `GET /api/merchant/stats` | covered in `tests/test_sale_events.py` |
| W3-3 | — | `GET /api/merchant/statement`, `POST /api/statements/verify`, `GET /api/admin/venues/{id}/statement` | `tests/test_statement.py` (13) |

90 backend tests pass; the Flutter suite is 35. Migration `0014` rolls forward and
back on both SQLite and Postgres, and the endpoints were exercised against a live
server on Postgres 15.

### Decisions taken during implementation

- **`merchant_stats` keeps `revenue` meaning exactly what it meant before**:
  money that actually arrived through Djassa. The declared half is reported
  beside it (`declared_revenue`, `turnover`, `verified_share`) rather than folded
  in, so no existing client silently starts reading a larger number, and an
  aggregator confirmation is never summed with a typed figure into one
  unqualified total.
- **Quarantine got an endpoint and a periodic warning**, not just a migration
  log line. The plan said to count and report unresolvable rows; a count printed
  once during a deployment is a count nobody reads, so
  `GET /api/admin/sale-events/quarantined` shows the backlog and
  `sale_events.report_quarantine` logs it until it is zero.
- **An ambiguous merchant is quarantined too.** The plan covered declared sales
  with *no* resolvable venue. Two venues sharing one `merchant_id` is the same
  problem wearing a different hat: `MIN(id)` would have silently credited one
  merchant with another's sales, so the backfill resolves only where exactly one
  venue claims the id.
- **`sale_events.amount` is `Numeric`, not `Integer`.** XOF has no minor unit, but
  the declared stream being absorbed allowed two decimal places, and a migration
  that rounded would lose money that was really taken. Verified against Postgres
  with a `1500.40` legacy row.
- **Statement amounts are normalized strings.** Postgres and SQLite return the
  same amount at different scales (`7000` vs `7000.0000000000`), and since those
  bytes are what gets signed, the two databases would otherwise produce different
  signatures for the same business.
- **HMAC, not a public-key signature.** A verifier must ask Djassa, so it proves
  "this is the document Djassa issued" rather than "only Djassa could have made
  it". Right trade for a pilot — no key distribution — and the payload carries
  `algorithm` and `key_id` so the swap to Ed25519 is a one-line change when a
  partner wants to verify offline.
- **A missing signing secret refuses the statement (503)** rather than issuing an
  unsigned one. An unsigned attestation would reach a lender looking exactly as
  official as a real one.
- **A window too dense to aggregate is refused (413), never truncated.** Not in
  the plan, but the statement signs whatever total it is handed, and a truncated
  event set still sums to a *plausible* turnover. A signed document understating a
  merchant's revenue because a query hit a row limit is the worst failure this
  code could have, so `events_in_window` raises rather than answering. The old
  export's silent `LIMIT 10000` is gone for the same reason.
- **The statement has a 28-day minimum period.** Regularity is half of what the
  document is for, and a three-day window cannot speak to it — issuing one anyway
  would produce a misleading artifact that still carried a valid signature.
- **An admin can issue a statement for any venue, on any plan.** Pilot reality: a
  partner conversation happens with Djassa in the room, and a starter-plan
  merchant still needs their history to exist. Audited identically.
- **The per-customer export now carries a `source` column** and cash sales are
  absent from it entirely — an anonymous counter sale has no data subject, so
  there is nobody who could have consented to it.
- **`Transaction` and `POST /api/transactions` are deprecated, not deleted**, per
  the plan's rollback-safety note. GraphQL `myTransactions` and `syncTransactions`
  carry `deprecation_reason`; `mySales` is the replacement and takes no merchant
  id.
- **`recordSale` lost its `merchantId` parameter** in the retailer app, and the
  local `sales.merchant_id` column is now written as `0` and never read. It could
  not be dropped: `minSdk 21` means SQLite older than 3.35 (no `DROP COLUMN`), and
  `database.dart` rightly forbids recreating `sales` — a merchant upgrading with
  unsynced sales must not lose them.
- **The app now sends `occurred_at`.** The server records its own `recorded_at`
  alongside, so a sale queued overnight counts on the day it was made and the gap
  stays visible as the offline-window signal (`median_recording_lag_hours`).

### Not done in Phase 2

- **The `_DEMO_USERS` blocker still stands.** Three hardcoded logins remain a hard
  blocker for a real pilot. Still tracked as its own item, still out of scope here.
- **Multi-outlet is still one venue per login.** `_my_venue` resolves the caller's
  venue with `.first()`, so a merchant owning two outlets sees only one — every
  Phase 2 endpoint inherits that. `Feature.MULTI_OUTLET` is defined as a plan
  entitlement but the feature behind it does not exist yet, unchanged from Phase 1.
- **Quarantined rows have no resolution endpoint**, only visibility. Attaching one
  to a venue is a judgement call about whose money it was; the deliberate choice
  was to surface the backlog rather than build a tool that makes guessing easy.
- **Seed data does not create sale events.** A fresh dev database starts with an
  empty stream; recording a sale or paying a QR fills it. Seeding turnover would
  put invented revenue into a document whose whole purpose is being trustworthy.
- **`GET /api/merchant/statement` is JSON only.** A PDF is what a credit officer
  will eventually want, but the signature covers the JSON payload, and rendering
  is a presentation concern to settle with the first partner.

---

# Phase 3 — Real money movement (external dependency)

## W3-4 — Aggregator integration *(blocked on the partner; open the request on day one)*

`MOBILE_MONEY_PROVIDER` supports only `fake`; `cinetpay` raises "not implemented yet". This gates
revenue lines 1, 3 and 5. **The sandbox request is the single most time-critical non-code action in this
plan** — it should be sent before W1-1 starts, because the waiting is the cost, not the coding.

Ask for, per [Partners and outreach plan](../business/PARTNERS.md): sandbox credentials, webhook
signature scheme, settlement timing, transaction limits, reconciliation and incident support, **and the
commission split for a partner-reseller arrangement**. Negotiate the split *before* volume exists —
after, the leverage is gone.

**Code** — `app/services/mobile_money.py`, implementing `CinetPayProvider` against the existing
interface. The surrounding architecture is already correct: pending row persisted before the outbound
call, idempotency key threaded through, production refusing the fake provider. Preserve all three.

Webhook handling already has idempotency and a processing log — reuse them rather than adding a path.

**Tests** — signature verification rejects a forged webhook; a replayed webhook settles once; a
timeout leaves a reconcilable pending row; a declined payment awards no points.

**Done when:** a real 100 XOF payment moves customer wallet → merchant wallet, points are granted once,
and a `sale_event` with `source = 'mobile_money_confirmed'` exists. Djassa's balance is unchanged — that
last clause is the compliance test, and it should be verified explicitly, not assumed.

## W1-3 — Commission and recurring collection *(after W3-4)*

- Record the commission Djassa earns per settled payment (revenue line 1) as a derived figure from the
  aggregator's statements — **never** as a deduction from the customer's payment.
- Recurring mobile-money collection for subscriptions (W1-2), replacing manual recording.
- Reconcile monthly: aggregator statement vs `billing_events`.

---

# W4 — Concept and pilot optimization (non-code, start now)

These are the "best steps to optimize the concept" and none of them wait for code.

## W4-1 — Narrow the pilot from six categories to two *(decision, this week)*

`CATEGORIES` spans maquis, supérette, pharmacie, mode, beauté, téléphonie — which contradicts the
cluster-density thesis in [Product concept](../business/CONCEPT.md).

- Pilot **maquis + supérette, one or two communes**: high repeat frequency, small tickets, exactly what
  the recording habit needs.
- Keep pharmacie in the app as an **acquisition hook only** (see W4-2), not a loyalty target — low visit
  frequency, regulated pricing, and prescription data is a privacy exposure not worth taking in a pilot.
- Hide mode, beauté, téléphonie from the pilot build. Keep the code; narrow the config.

## W4-2 — Treat pharmacie-de-garde as its own asset *(this week)*

The only feature with daily urgent pull, no official API, no competitor holding it. Potentially
sponsorable (pharmacy group, health insurer, mutual).

- Name an owner for the **weekly manual rotation entry** and cost it per month. It is a real recurring
  operating cost currently absent from every unit-economics figure.
- Decide whether it is free reach (recommended for the pilot) or sponsored inventory (later).

## W4-3 — Instrument the master metric's denominator *(with W3-1)*

[djassa-product-concept-v2.md](../business/CONCEPT.md) says the share of real transactions
recorded governs everything — but nothing captures **total real sales**, so it cannot be computed and
the phase gate cannot be enforced.

- Add a pilot-only daily merchant self-report: "roughly how many sales today?" One tap, end of day.
- This is the one justified exception to the no-new-habit rule, it is pilot-scoped, and it should be
  removed once digital share is high enough to make it moot. Say so in the code comment.

## W4-4 — Test pricing and revenue share with merchants *(before W1-2 hardens)*

Per [Business model](../business/BUSINESS-MODEL.md), pricing is an experiment, not a decision. Ask 5–10 pilot
merchants directly:

- Featured-slot price per week (W1-1 needs a number).
- **Revenue share versus fixed subscription** — the review's recommended first line is commission, and
  no merchant has been asked whether they prefer it. This single answer reorders the revenue lines.
- What they would pay for a revenue statement that helps a credit application.

## W4-5 — Cap the points liability *(with W1-2)*

`points_per_100` has no ceiling and `LoyaltyEntry` has no expiry, so a merchant accrues unbounded,
indefinitely-lived liability. Expect it as a sales objection from any merchant who thinks it through.
Add point expiry and a maximum redemption rate per visit or period — a schema and policy decision, so
decide it before merchants accumulate balances under the old rules.

## W4-6 — Resolve djassa / dkassa, and update the concept docs *(before institutional outreach)*

- Settle the name, check trademark availability — already an open item in [concept.md](../business/CONCEPT.md).
- Once W3-1 lands, correct [djassa-product-concept-v2.md](../business/CONCEPT.md) so its
  single-primitive claim matches the implementation. Right now the document describes an intent, not the
  system; after W3-1 it describes both.
- State finding 4 explicitly in the concept: **loyalty points are the incentive that buys the
  cash-to-digital behaviour change.** That is loyalty's real job in this design and it belongs in writing.

---

# Suggested sequence

Assumes one developer on code, one person on W4. Weeks are indicative.

| Week | Code | Concept / commercial |
|---|---|---|
| 0 | — | **Send the aggregator sandbox + commission request (W3-4 prerequisite).** W4-1, W4-2, W4-4 interviews |
| 1 | W1-1 featured-slot billing | W4-4 pricing answers land; set slot inventory and price |
| 2 | W2-1 export authorization fix | W4-5 points-liability policy decision |
| 3 | W1-2 subscription and billing records | W4-6 name decision |
| 4–5 | W3-1 event-stream merge (+ retailer app) | W4-3 denominator self-report design |
| 6 | W3-2 verified revenue share | Draft the IMF conversation around the statement |
| 7 | W3-3 signed revenue statement | Doc corrections (W4-6 second half) |
| 8+ | W3-4 aggregator, then W1-3 commission | Pilot launch in the narrowed corridor |

**Critical path:** the aggregator request (week 0, external) and the W3-1 merge (weeks 4–5, internal).
Everything else can slip without blocking anything downstream.

# Decision gates

Do not pass a gate on partial evidence — the whole point of the phasing in
[Roadmap](../business/ROADMAP.md) is that each gate is load-bearing.

**Gate A — before any partner demo:** W2-1 merged; no path to another merchant's customer data; exports
audited. *Do not demo the export before this.*

**Gate B — before the IMF conversation:** W3-1, W3-2, W3-3 merged; statement numbers reconcile with the
event stream; verified share measurable per venue.

**Gate C — before scaling beyond the pilot corridor:** the master metric computable (W4-3) and healthy;
merchants paying (W1-1 or W1-2 with real `billing_events`); support and messaging cost per outlet known.

**Gate D — before any credit or savings referral revenue:** signed partner agreement, regulatory review,
consent flow implemented and audited, and Gate B passed. Per the review, this line stays out of a
year-1 forecast.

# Explicitly not now

Restating the non-scope so this plan cannot be read as licence to build it:

- Direct lending, or Djassa holding savings — requires BCEAO authorization it does not have.
- Points-to-cash conversion.
- Selling identifiable transaction data.
- Charging the customer a fee to pay — cash wins instantly.
- The federated identity layer. It remains a strategic hypothesis; entry conditions are in
  [Roadmap](../business/ROADMAP.md) and none are met.
- Tontine beyond what exists, until the merchant product shows willingness to pay.
- A second country.

# Open decisions this plan cannot make

1. **Revenue share or subscription first?** W4-4 answers it. It changes whether W1-2 or W3-4 is the
   priority.
2. **Is the aggregator commission split available at pilot volume?** If not, the subscription line
   carries the pilot alone.
3. **Featured-slot inventory and price** — blocks W1-1 going live, not W1-1 being built.
4. **Who enters the pharmacy rotation weekly, at what monthly cost?**
5. **Real merchant accounts** — `_DEMO_USERS` is three hardcoded logins. Needed before W3-4; not
   scoped here.

---

Related documents:

- [Concept review and optimization proposals](optimization_claude_djassa.md) — the findings this plan acts on
- [Product concept v2](../business/CONCEPT.md) · [Product concept](../business/CONCEPT.md)
- [Business model](../business/BUSINESS-MODEL.md) · [Product roadmap](../business/ROADMAP.md)
- [Financial inclusion scope (FR)](../business/CONCEPT.md) — the non-negotiable constraints
- [Partners and outreach plan](../business/PARTNERS.md) — what to ask the aggregator and the IMF
- [Technical guide](../technical/TECHNICAL-GUIDE.md) — local development and migration workflow
