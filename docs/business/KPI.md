# Hossouko — Key Performance Indicators

This document defines what Hossouko measures, how each number is computed, where the data lives in the platform, and what value moves a phase gate. It turns the metric lists in [BUSINESS-MODEL.md](BUSINESS-MODEL.md#unit-economics) and [ROADMAP.md](ROADMAP.md) into one scorecard.

*Last updated: 6 October 2026. Stage: pre-pilot (Phase 0).*

**How to read the targets.** Hossouko has no pilot data yet. Every target here is one of three kinds, and is labelled as such:

- **Gate**: already decided in [ROADMAP.md](ROADMAP.md) or [BUSINESS-MODEL.md](BUSINESS-MODEL.md#decision-gates).
- **Proposed**: a starting threshold for the pilot, to be replaced by the pilot's own baseline after 60 days.
- **Benchmark**: an external reference (sources in [§ 10](#10-external-benchmarks-and-sources)). Most come from global SaaS, app or mobile-money data and do **not** describe Ivorian neighbourhood merchants. Use them for orientation only, never in investor or partner material as if they were Hossouko's own results.

---

## 1. Principles

1. **One North Star.** Every other KPI either explains it, makes it cheaper, or proves it is not being gamed.
2. **Activity over sign-ups.** In merchant payments, most signed-up merchants never transact (CGAP cites a provider where only 15% of 100,000 merchants transacted monthly). We count *active* outlets, never registered ones, in any external figure.
3. **Evidence is labelled.** Sales are never summed across `mobile_money_confirmed` and `cash_declared` without showing the split, exactly as `SaleEvent` stores them.
4. **Per outlet, then per corridor.** The pilot is judged merchant by merchant. Averages hide the one merchant who records 90% next to ten who record 10%.
5. **Gender on every financial KPI.** It is a design constraint ([CONCEPT.md § 8](CONCEPT.md#8-the-path-to-financial-inclusion)), so every Phase 3+ KPI is reported split by women and men. The platform cannot do this yet (see [§ 9](#9-measurement-gaps)).
6. **Counter-metrics are mandatory.** Each growth KPI has a guardrail that catches harm: points liability, notification cost, consent withdrawal, re-borrowing.
7. **No KPI justifies crossing a red line** ([CONCEPT.md § 11](CONCEPT.md#11-red-lines)).

---

## 2. KPI tree

```text
                    NORTH STAR
       % of a merchant's real sales recorded in Hossouko
                         │
     ┌──────────────┬────┴─────────┬───────────────┬───────────────┐
     ▼              ▼              ▼               ▼               ▼
  Merchant       Customer &     Revenue &       Evidence        Platform &
  adoption       loyalty        unit economics  quality & trust reliability
  (§ 4)          (§ 5)          (§ 6)           (§ 7)           (§ 8)
     │              │              │               │
  active outlets  repeat-visit   MRR, renewal,   confirmed share,
  speed to record lift, points   CAC payback,    consent, audit,
  offline lag     liability      cost per outlet reconciliation
                                                   │
                                     Later phases (§ 3.3): tontine,
                                     reliability indicator, partner finance
```

---

## 3. The scorecard by phase

Track only what the current phase needs. A KPI from a later phase stays off the dashboard until its phase starts.

### 3.1 Phase 0 — Discovery (now)

| KPI | Definition | Target |
|---|---|---|
| Merchant interviews completed | Interviews in the chosen corridor and segment | 5–10 (**Gate**) |
| Willingness to pay | Share of interviewed merchants who accept a price within the [pricing experiment](BUSINESS-MODEL.md#pricing-experiment) range | ≥ 50% (**Proposed**) |
| Baseline repeat-visit rate | Merchant's own estimate of how many customers return within 30 days, recorded **before** Hossouko | Recorded for every pilot merchant (**Gate**: needed for the before/after comparison) |
| Baseline daily sales and wallet share | Tickets per day, average basket, % paid by mobile money | Recorded for every pilot merchant |
| Real cost per loyalty notification | Quoted bulk-SMS and WhatsApp Business price per message in Côte d'Ivoire | Known before Phase 1 |
| Partner confirmations | Payment partner, Wave webhook access, ARTCI review | All answered (**Gate**: no blocker on data or funds flow) |

### 3.2 Phase 1 and 2 — Merchant MVP, operations

The core dashboard. Definitions are in §§ 4–8.

| Area | KPI | Target |
|---|---|---|
| North Star | Recorded share, per merchant | High and growing for 60+ days (**Gate**). Proposed: ≥ 70% at day 30, ≥ 85% at day 60 |
| Adoption | Active outlets (30-day) / enrolled outlets | ≥ 80% in the pilot (**Proposed**) |
| Adoption | Merchant retention at 30 / 60 / 90 days | ≥ 90% / 80% / 75% (**Proposed**) |
| Loyalty | Repeat-visit rate of identified customers vs baseline | Positive lift the merchant can state (**Gate**). Proposed: +5 pts at a maquis, +3 pts at a pharmacy, matching the [value equation](BUSINESS-MODEL.md#why-a-merchant-pays-the-value-equation) |
| Revenue | Free-to-paid conversion | ≥ 40% of active pilot outlets (**Proposed**) |
| Revenue | Renewal | 3 consecutive months (**Gate**) |
| Cost | Notification cost per active outlet | < 30% of the outlet's subscription (**Proposed**) |
| Cost | CAC | < 12 months of expected gross profit per outlet (**Gate**) |
| Payments | Payment success rate | ≥ 95% (**Proposed**) |
| Trust | Exports with an audit record | 100% (**Gate**: hard rule) |

### 3.3 Phases 3–5 — Tontine, reliability indicator, partner finance

| Phase | KPI | Target |
|---|---|---|
| 3 Tontine | Active members after 90 days | Defined at Phase 3 start (**Gate**: measured) |
| 3 Tontine | Cycles completed without incident | ≥ 95% (**Proposed**) |
| 3 Tontine | On-time contribution rate | Baseline from pilot groups |
| 3 Tontine | Women's share of members | Reported every month (**Gate**) |
| 4 Indicator | Users who viewed their indicator explanation | ≥ 50% of those who have one (**Proposed**) |
| 4 Indicator | Appeals and corrections, and time to resolve | All resolved < 15 days (**Proposed**) |
| 4 Indicator | Indicator gap by ticket-size quintile and by gender | No penalty for small tickets (**Gate**: bias monitoring) |
| 5 Finance | Qualified, consented referrals → applications → approvals | Funnel tracked per partner (**Gate**) |
| 5 Finance | Merchants who obtained credit through their Hossouko history | Tracked (**Gate**) |
| 5 Finance | Portfolio at risk > 30 days (PAR30), where the partner may share it | Benchmark: microfinance PAR30 is typically under 5%; the partner's own figure applies |
| 5 Finance | Re-borrowing within 7 days of repayment | Flagged, never targeted (responsible-credit guardrail) |
| 5 Finance | Commission revenue / subscription revenue | Reported; **never** assumed in the plan before a signed agreement |
| 5 Finance | Women's share of referrals, approvals, average amount, repeat borrowing, PAR | Reported per partner (adapted from the WWB "Select Five") |

### 3.4 Layaway test

Runs only at shops where an admin switched it on. Read from `GET /api/admin/layaway`.

| KPI | Definition | Target |
|---|---|---|
| Plans started, by status | open, completed (paid, not yet handed over), delivered, cancelled | Tracked |
| Completion rate | Delivered ÷ (delivered + cancelled) | ≥ 70% (**Proposed**) |
| Overdue open plans | Open plans past their end date | 0 for more than 7 days |
| Median days to complete | Opening → last installment | Tracked |
| Value started and value paid | Sum of prices; sum of installments | Tracked |
| Disputes | Plans where the customer and merchant disagree on what was paid | < 5% of plans (**Proposed**); not in the platform yet, logged by support |
| New customers brought | Customers whose first record at the shop is a plan | Asked of each merchant |
| Women's share of plans | | Needs the gender field ([§ 9](#9-measurement-gaps)) |

---

## 4. Merchant adoption and engagement

| KPI | Formula | Source in the platform | Status |
|---|---|---|---|
| **Recorded share** (North Star) | Sales the server holds for a day ÷ the merchant's end-of-day estimate (`daily_report`), per merchant, over report days | `GET /api/admin/usage?app=retailer` → `merchants[].recorded_share`; `sale_events` + `usage_events` | **Live** (pilot-only self-report, see [action plan W4-3](../planning/action_plan_claude_hossouko.md)) |
| Enrolled outlets | Venues created, excluding `is_sample` | `venues` | Live |
| Activation rate | Outlets with ≥ 1 recorded sale within 7 days of enrolment ÷ enrolled | `venues.created_at`, `sale_events` | Computable (query) |
| Time to first sale | Enrolment → first `SaleEvent` | as above | Computable |
| Active outlets (7 / 30 / 90-day) | Outlets with ≥ 1 `SaleEvent` in the window (same 30/90-day convention GSMA uses for mobile money) | `sale_events` | Computable |
| Active days per outlet | Days with app activity in the window | `merchants[].active_days` | Live |
| Sales per active outlet per day | `SaleEvent` rows ÷ active days, split by `source` | `sale_events` | Computable |
| Median seconds to record a sale | From the `sale_recorded` event | `merchants[].median_sale_seconds` | Live. Proposed target: ≤ 10 s |
| Sale abandon rate | `sale_abandoned` ÷ `sale_form_opened` | `merchants[]` | Live. Proposed: < 10% |
| Offline lag | p50 / p95 of `recorded_at − occurred_at` | `sale_events` | Computable. Watch for batches older than 7 days |
| Merchant retention 30 / 60 / 90 | Outlets active in month *n* ÷ outlets active in their first month, by enrolment cohort | `sale_events` | Computable |
| Cashier adoption | Outlets with ≥ 1 active `VenueStaff` | `venue_staff` | Computable |
| Enrolment funnel | Partner requests → approved → first sale, and time to decision | `partner_requests`, `venues` | Computable |
| Agent productivity | Outlets enrolled and still active at 30 days, per field agent | `venues.enrolled_by` | Computable |

---

## 5. Customer and loyalty

| KPI | Formula | Source | Status |
|---|---|---|---|
| **Repeat-visit rate (identified customers)** | Customers with ≥ 2 visits at an outlet within 30 days ÷ customers with ≥ 1 visit, compared with the Phase 0 baseline | `sale_events.customer_id`, `loyalty_entries` | Computable; baseline is collected by hand |
| Identified share of sales | `SaleEvent` with a `customer_id` ÷ all sales, per outlet | `sale_events` | Computable |
| Loyalty consent rate | Consents granted ÷ customers asked, split `app` / `counter` | `loyalty_consents` | Partial: "asked" is not logged |
| Consent withdrawal rate | Withdrawn ÷ granted, monthly | `loyalty_consents.withdrawn_at` | Computable. Rising rate = trust alarm |
| Points issued and redeemed | Sum of positive and negative `LoyaltyEntry.points`, per outlet | `loyalty_entries` | Computable |
| Redemption rate | Points redeemed ÷ points issued, trailing 90 days | `loyalty_entries` | Computable. Benchmark: ~60% across loyalty platforms |
| Time to first reward | First visit → first `redeem` entry | `loyalty_entries` | Computable. Target from concept: 3–5 visits (maquis), 2–3 (pharmacy) |
| **Outstanding points liability** (counter-metric) | Unredeemed points × reward value per point, per outlet | `loyalty_entries`, `loyalty_rewards` | Computable. Points have no expiry yet ([W4-5](../planning/action_plan_claude_hossouko.md)) |
| Reward cost as a share of member sales | Value of rewards redeemed ÷ sales by identified customers | as above | Computable |
| Customer app installs and active installs (1 / 7 / 30-day) | First launches, installs with activity in the window | `GET /api/admin/usage?app=user` | Live |
| Customer app retention D1 / D7 / D30 | Installs active on day *n* after install, by install cohort | `usage_events` | Computable. Benchmark (global finance apps): D1 ≈ 22%, D30 ≈ 4% |
| Discovery use | Venue views, deal opens, pharmacy-duty views per active install | `usage_events` | Live |
| Scan → payment conversion | `payment_completed` ÷ `scan_opened` | `usage_events` | Live |

---

## 6. Revenue and unit economics

All amounts in XOF. "Outlet" means one paying venue.

| KPI | Formula | Source | Status |
|---|---|---|---|
| **MRR** | Sum of monthly amounts of `active` subscriptions | `GET /api/admin/revenue` → `mrr` | Live |
| Active paying outlets, by plan and status | | `/api/admin/revenue` → `outlets_by_plan`, `outlets_by_status` | Live |
| Collected in window, unpaid invoices and amount | | `/api/admin/revenue` | Live |
| Free-to-paid conversion | Outlets reaching `active` ÷ outlets that finished their trial | `merchant_subscriptions`, `billing_events` | Computable |
| Renewal rate | Subscriptions paid for period *n+1* ÷ due for period *n+1* | `billing_events` (`invoice_due`, `paid`) | Computable |
| Logo churn (monthly) | Outlets moved to `cancelled` ÷ paying outlets at month start | `merchant_subscriptions` | Computable. Benchmark: SMB SaaS 3–7% per month |
| Net revenue retention | MRR this month from last year's (or last quarter's) cohort ÷ that cohort's starting MRR | `billing_events` | Computable once there is a year of data. Benchmark median ≈ 101% |
| ARPU per paying outlet | MRR ÷ paying outlets | derived | Live |
| Sponsored placements sold, revenue, paid rate | Placements with `paid_at` set, price sum | `deal_placements` | Computable |
| **CAC per outlet** | (Field-agent pay, reseller commission, materials, travel) ÷ outlets that became active | Not in the platform | **Gap** |
| CAC payback | CAC ÷ monthly gross profit per outlet | derived | Gap until CAC exists. Gate: < 12 months. Benchmark (early-stage SaaS): 18–24 months, so Hossouko's gate is deliberately stricter |
| **Notification cost per active outlet** | SMS + WhatsApp spend attributed to an outlet ÷ active outlets | Not in the platform (OTP spend is only budget-capped) | **Gap** |
| Support cost per outlet | Support hours × cost ÷ active outlets; support requests per outlet | `support_requests` (count only) | Partial |
| Payment cost per transaction | Aggregator fees on Hossouko-route payments ÷ payments | provider reports | Gap |
| Gross margin by plan | (Plan revenue − notification, payment, hosting and support costs) ÷ plan revenue | derived | Gap |
| **Contribution margin per corridor, excluding credit commissions** | | derived | Gate: positive before expansion |
| LTV : CAC | (ARPU × gross margin ÷ monthly churn) ÷ CAC | derived | Benchmark: ≥ 3 : 1 for SMB SaaS |

---

## 7. Evidence quality, trust and compliance

This is what a lender, ARTCI or BCEAO will check. These KPIs are what makes the history worth anything.

| KPI | Formula | Source | Target |
|---|---|---|---|
| **Confirmed share of recorded value** | `mobile_money_confirmed` amount ÷ all recorded amount, per outlet | `sale_events.source` | Rising over time; reported next to every revenue history |
| Quarantined legacy sales | Count and amount with `status = quarantined` | `sale_events` | Falling to 0 |
| Duplicate sale attempts refused | Idempotency replays with a different payload | API logs / `idempotency_hash` refusals | Monitored, not targeted |
| Exports with audit record | Audited exports ÷ exports | `export_audits` | 100% |
| Customer-level exports with valid consent | | `export_audits`, `consents` | 100% |
| Data-subject requests (access, correction, withdrawal) answered on time | | manual log | 100% within the ARTCI deadline |
| OTP verification rate | `otp_verify ok` ÷ `otp_request sent` | `hossouko_auth_events_total` | Alert below 30% (SMS pumping) |
| SMS spend vs daily budget | | `OTP_DAILY_SMS_BUDGET`, alert `OtpDailyBudgetReached` | Never reached in normal use |
| Account recoveries: time to decision | `recovery_requests` | | Proposed: < 48 h |
| Security incidents, and time to close | | incident log | 0 critical open |

---

## 8. Platform and payment reliability

Most of these already have alerts in [monitoring/ALERTS.md](../../monitoring/ALERTS.md).

| KPI | Source | Target |
|---|---|---|
| API availability | Uptime monitor on `/ready` | ≥ 99.5% monthly (**Proposed** for the pilot) |
| 5xx error rate | `http_requests_total` | < 1%; alert at 5% |
| p95 latency | `http_request_duration_seconds` | < 1 s; alert at 2 s |
| Payment success rate | `customer_payments.status` | ≥ 95% |
| Webhook refusals | `PaymentWebhookFailing` | 0 sustained |
| Reconciliation match rate | `payment_reconciliations` against settlement reports | 100% matched or explained (not built yet: [ROADMAP gap 4](ROADMAP.md#where-we-stand)) |
| Refund and dispute rate | `payment_refunds`, `payment_disputes` ÷ payments | Monitored |
| Crash-free sessions per app version | `client_events`, Play Console vitals | ≥ 99% |
| **Data used per active user per day** | `data_kb_per_active_install_day`, `merchants[].data_kb_per_active_day` | Proposed: < 1 MB/day merchant app. Prepaid data is a real cost for the user |
| Sync success | Sales accepted ÷ sales sent by the merchant app | ≥ 99.9% |

---

## 9. Measurement gaps

What this scorecard needs and the platform cannot produce yet, in priority order.

| Gap | Why it matters | Proposed fix |
|---|---|---|
| **No gender field** on users, venues or partner requests | Gender reporting is a design constraint and every institutional partner (APIF, Fin'ELLE, SGPME) will ask for it | Optional, self-declared field on the merchant enrolment and the user profile, with consent and a "prefer not to say" option; never used in any score |
| **No acquisition cost record** | CAC and the unit-economics gate cannot be computed | Log agent and reseller payments per enrolled outlet (`venues.enrolled_by` already names the agent) |
| **No notification cost record** | The [hidden risk](BUSINESS-MODEL.md#why-a-merchant-pays-the-value-equation) in the model | Record each paid SMS/WhatsApp send with its venue and unit cost |
| No log of consent *requests* | Consent rate has no denominator | Event when the counter or app shows the consent prompt |
| No pre-Hossouko baseline in the platform | The repeat-visit lift is the number that sells the subscription | Phase 0 interview form, stored per venue |
| Points never expire | Liability grows without limit | Expiry and redemption cap ([W4-5](../planning/action_plan_claude_hossouko.md)) |
| No reconciliation with settlement reports | Confirmed revenue cannot be certified | Phase 1 payment work |
| No KPI dashboard combining billing and usage | The gate review needs one page | One admin endpoint or Grafana dashboard over the queries above; `investor_room_metrics` stays curated by hand ([INVESTOR-ROOM-SETUP.md](INVESTOR-ROOM-SETUP.md)) |

---

## 10. External benchmarks and sources

| Benchmark | Value | Applies to | Source |
|---|---|---|---|
| Merchants transacting monthly after sign-up | 15% at one provider with 100,000 merchants | Mobile-money merchant acceptance in developing markets | CGAP, *Digitizing merchant payments: what will it take?* |
| Active account definitions | ≥ 1 transaction in the last 30 or 90 days | Mobile money industry standard | GSMA, *State of the Industry Report on Mobile Money* |
| Global mobile-money 30-day activity rate | 25.7% (2025) | Registered → active mobile-money accounts | GSMA, *State of the Industry Report 2026* |
| SMB SaaS monthly logo churn | 3–7% | Global B2B SaaS selling to small businesses | SaaS benchmark compilations, 2025–2026 |
| Net revenue retention, median / top | ~101% / ≥ 120% | Global SaaS | as above |
| CAC payback, early stage | 18–24 months | Global SaaS | as above |
| LTV : CAC | ≥ 3 : 1 | SMB SaaS | as above |
| Loyalty redemption rate | ~60% average | Loyalty platforms, mostly retail | Spendgo |
| Finance app retention | D1 ≈ 22%, D30 ≈ 4% | Global finance apps | App retention benchmark compilations, 2025 |
| Gender indicators | % new women borrowers, average loan size, retention, PAR and staff retention for women | Microfinance institutions | Women's World Banking and MIX, *Select Five Gender Performance Indicators* |
| Portfolio at risk > 30 days | Most common MFI loan-quality indicator | Microfinance | MIX / MicroFinance Gateway |
| Endowed progress effect | 34% completion with pre-stamped cards vs 19% | Loyalty card design | Field study cited in [MARKET.md § 9](MARKET.md#9-evidence-for-the-hossouko-model) |

Links:

- CGAP — [Digitizing merchant payments: what will it take?](https://www.cgap.org/sites/default/files/publications/slidedeck/digitizingmerchantpaymentswhatwillittake-170907135915.pdf) · [Merchant payments blog series](https://www.cgap.org/blog/series/merchant-payments-how-unlock-space)
- GSMA — [State of the Industry Report on Mobile Money](https://www.gsma.com/sotir/) · [Defining active customers](https://www.gsma.com/mobilefordevelopment/programme/mobile-money/defining-active-customers-clarification-on-how-operators-can-monitor-mobile-money-activity-rates/)
- SaaS metrics — [SaaS metrics guide: NRR, LTV:CAC and cohort analysis 2026](https://fungies.io/saas-metrics-guide-nrr-ltv-cac-cohort-analysis-2026) · [SaaS Hero GTM metrics 2026](https://www.saashero.net/uncategorized/gtm-saas-metrics-2026/)
- Loyalty — [Spendgo: average loyalty redemption rate](https://resources.spendgo.com/blog/understanding-average-loyalty-program-redemption-rate-tips-for-improving-yours) · [BonusQR: loyalty KPIs for small business](https://bonusqr.com/article/loyalty-program-kpis-metrics-that-grow-your-business)
- App retention — [Enable3: app retention benchmarks 2025](https://enable3.io/blog/app-retention-benchmarks-2025)
- Gender — [Select Five Gender Performance Indicators](https://findevgateway.org/paper/2014/07/select-five-gender-performance-indicators) · [Financial Alliance for Women: value of sex-disaggregated data](https://financialallianceforwomen.org/?p=4297)
- Microfinance — [Digital Financial Services measurement framework](https://www.findevgateway.org/paper/2019/10/digital-financial-services-measurement-framework)

Re-verify every external figure before it appears in investor, partner or regulatory material, as for [MARKET.md](MARKET.md).

---

## 11. Review rhythm

| Cadence | Who | What |
|---|---|---|
| Daily (pilot) | Ops | Active outlets, sync errors, payment failures, alerts |
| Weekly | Team | North Star per merchant, repeat-visit lift, abandons, support requests. The merchant gets their own "customers who came back" number the same week |
| Monthly | Team + advisors | MRR, conversion, renewal, churn, cost per outlet, points liability, consent withdrawals |
| At each gate | Founders, partners | The phase scorecard in § 3, with the evidence behind each number |

When a KPI changes definition, record the date and the reason here, so a trend never silently mixes two definitions.

## Related documents

[CONCEPT.md](CONCEPT.md) · [BUSINESS-MODEL.md](BUSINESS-MODEL.md) · [ROADMAP.md](ROADMAP.md) · [Technical guide § usage](../technical/TECHNICAL-GUIDE.md) · [Monitoring alerts](../../monitoring/ALERTS.md)
