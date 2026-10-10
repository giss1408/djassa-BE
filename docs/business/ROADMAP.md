# Fidelia — Roadmap

A phase is complete when **real users have validated it**, not when the code ships. Each phase has an exit gate, and no phase starts before the previous one is validated. Phase numbering matches the public site (`fidelia-Web`).

*Last updated: 30 September 2026.*

## Where we stand

**Stage: pre-pilot.** Phase 0 is in progress. The prototype is ahead of the business validation: several later-phase foundations exist in code, but none is exposed to real users or real money.

| Area | State | Notes |
|---|---|---|
| Merchant app: offline sale recording and batched sync | **Built, verified on a real device** | Galaxy A51 against the live backend; a dropped response after commit does not create a duplicate |
| Merchant app: deals ("bons plans") | Prototype | Create and list deals |
| Customer app: venues, search by dish or commune | Prototype | Demo data |
| Customer app: on-duty pharmacies | Prototype | Weekly rotation entered by an admin from the official list; no official API exists |
| Customer app: QR payment, receipt, points, rewards | Prototype, **sandbox only** | No live payment provider; money would flow wallet to merchant wallet |
| Deals with a paid featured slot | Prototype *(integration)* | Sold as a placement with a time window, price and paid status; expires on its own; slots capped per commune and category |
| **One sale stream** (`SaleEvent`) | Prototype *(integration)* | Every sale labelled `mobile_money_confirmed` or `cash_declared`, never summed into one unqualified total; merchant taken from the login, not from the request; legacy sales without a clear owner held in quarantine rather than guessed |
| Merchant subscriptions and billing ledger | Prototype *(integration)* | Plans, append-only billing events, admin revenue report (MRR, conversion, renewal); payment collected manually for the pilot. Recording sales and earning points are never behind a paywall |
| Consented revenue export with audit | Prototype *(integration)* | Default export names no customer; customer-level export needs each customer's consent; every export audited; consent can be withdrawn |
| Loyalty ledger and redemption | Prototype | Points awarded on customer payments |
| **Offer alerts and offer use at the counter** | Prototype *(integration)* | A deal is announced by push to the commune and the shop's followers (one per shop per day); the merchant records "Client venu" and whether the customer is new. Real pushes need a Firebase project (`PUSH_PROVIDER=fcm`, app `FIREBASE_*` defines) |
| **Points on cash sales, by phone** | Prototype *(integration)* | The merchant app sends the customer's number with a cash sale; the customer earns the venue's points; the merchant looks up the balance and hands over a reward at the counter. Not merged into customer-app accounts until an OTP-verified phone login exists |
| Layaway ("payer en plusieurs fois") | Prototype *(feature/kpis)* | One named good, fixed price, end date, terms accepted; installments recorded, one sale on handover; off unless an admin switches it on for the shop |
| Tontine groups, cycles, contributions, export | Foundation only | Built early; **not to be exposed before the Phase 3 gate** |
| Consent records, verification tiers (request only) | Foundation only | Tier 1 and 2 cannot be self-approved; they need a licensed KYC adapter |
| Payment state machine, signed and idempotent webhooks, refunds, disputes | Prototype | Reconciliation incomplete |
| Monitoring, CI/CD with SBOM and image scanning | Built | |
| Public site (FR/EN) | Built | |

**Known gaps blocking the pilot:**

1. **Authentication is a hardcoded demo user.** No registration, no phone/OTP Tier 0 login, no refresh token.
2. ~~Two data models are not yet linked.~~ **In progress on `integration`:** recorded sales and customer payments now write one `SaleEvent` stream, and the merchant app posts to it. Remaining: automatic Wave capture as a third source (gap 7), and resolving the quarantined legacy sales.
3. No outlet registration or onboarding flow (on `integration` the merchant is derived from the login, but accounts are still created by hand); points earned by phone at the counter are not yet visible in the customer app, because a Tier 0 profile declares a number without proving it (needs OTP login, gap 1).
4. No live payment provider (sandbox adapter only); no reconciliation with settlement reports.
5. No per-resource authorisation model; no production secrets or backups; no independent security review.
6. Dioula and other local-language support not started; no gzip on the API.
7. **No automatic capture of wallet payments.** Merchants' existing wallet QR payments (Wave first) do not yet flow into Fidelia. This is the zero-habit entry point the concept now prioritises (see [CONCEPT.md § 3](CONCEPT.md#3-the-idea-one-habit-five-uses)).

## Phase 0 — Discovery and compliance · *in progress*

**Goal:** confirm that the problem, users, partners and legal perimeter are real.

- 5 to 10 merchant interviews in one Abidjan commune; **maquis and grocery shops** (pharmacies are out of the pilot, see [CONCEPT.md § 12](CONCEPT.md#12-pilot-boundaries)) and one acquisition channel. Test the daily cash book as the first reason to sign up.
- **MFI test:** ask one or two MFIs (Fin'ELLE, Advans) whether they would pay for a consented tool to follow the sales of merchants they already lend to, and ask merchants whether they would accept it.
- **Plan B if Wave refuses:** confirm that merchants would still record cash sales; apply the stop-or-change rule in [CONCEPT.md § 12](CONCEPT.md#12-pilot-boundaries).
- A narrow pilot agreement.
- **Operator capabilities**: whether Orange Money and MTN MoMo can notify payments to a merchant's static QR (not only payments Fidelia starts), their merchant rates, and activation times.
- **PI-SPI status in Côte d'Ivoire** (the BCEAO's instant-payment interoperability platform, see [MARKET.md](MARKET.md#what-pi-spi-is)): how far interoperable merchant QR has rolled out, and which licensed payment institution could connect Fidelia to it.
- **Wave Business API access for pilot merchants**: can a small merchant enable the `merchant.payment_received` webhook for Fidelia, and may the customer phone number be used for loyalty (Wave terms, ARTCI)? This decides the Phase 1 architecture.
- Payment aggregator sandbox access (CinetPay or equivalent) as the fallback route, and confirmed PI-SPI compliance.
- Real cost per loyalty notification: local bulk SMS and WhatsApp Business rates for Côte d'Ivoire.
- Merchant willingness to pay against the pricing hypotheses in [BUSINESS-MODEL.md](BUSINESS-MODEL.md#pricing-experiment).
- Data inventory and consent design; ARTCI review.
- Identity and KYC boundary review with the payment partner.
- Regulatory review of the QR payment flow: confirm Fidelia's role as a technology partner and the direct wallet-to-wallet flow.
- Brand name confirmed.
- Baseline metrics and support process.

**Exit gate:** a pilot merchant group and a payment partner are identified; no unresolved blocker on the MVP data or funds flow.

## Phase 1 — Merchant MVP: record, pay, reward · *next*

**Goal:** record useful activity and create repeat usage.

- Tier 0 phone or operator-linked login for merchants and customers (replaces the demo user).
- Outlet registration and merchant QR code.
- **Automatic capture of the merchant's existing Wave payments** (signed webhook → event → points for the paying phone number). This is the priority entry point.
- **One merchant identity and one event stream** covering captured wallet payments, recorded cash sales and Fidelia-route payments.
- Loyalty rules, points and rewards for all entry points. New customers start with progress already made, and the first reward is reachable in 3–5 visits.
- **Customer app, focused scope** ([CONCEPT.md § 12](CONCEPT.md#12-pilot-boundaries)): map of pilot merchants with directions, free merchant offers with push notifications, on-duty pharmacies, points and rewards. Customers without the app identify by phone number at the counter. No WhatsApp or SMS alerts.
- **Offer use recorded at the counter** in the merchant app, to count the new customers the app brings.
- Merchant reporting: **daily cash book** (one total across every wallet and cash, the day-1 hook), a weekly report of **"customers who came back"** and **"new customers brought by Fidelia"**, and a signed, consented revenue statement for MFI demos.
- **Everything free during the pilot.** Billing and paid plans stay ready (subscription paid in mobile money) so the paid plan can be offered when the pilot ends.
- Offline queue and sync (built).
- Per-resource authorisation and ownership checks; production secrets.
- French first; Dioula for the merchant app.

**Measure:** % of real sales recorded (master metric) · repeat-visit rate of identified customers, before and after joining · notification cost per active outlet · active merchants · transactions per merchant · customer repeat rate · payment success rate · customer app installs active at 7 and 30 days · new customers brought by app offers · merchant retention 30/60/90 · **share of merchants accepting the paid plan at the end of the pilot** · support cost per outlet · data consumed per user.

**Identity gate:** no biometric or national-ID check for loyalty or payments; the operator identity signal and consent are defined before relying on them; duplicate-account prevention tested without exposing unnecessary data.

**Exit gate:** merchants record a high and growing share of real sales for 60+ days, and **accept the paid plan when the free pilot ends**.

## Phase 2 — Operations and network · *planned*

**Goal:** make the merchant product repeatable in the first corridor before adding financial complexity.

- First paid plans running; **paid featured placement** for offers in the customer app; lapsed-customer win-back offers by push notification; payment through Fidelia in the customer app.
- Association and merchant-referral onboarding; multi-outlet accounts.
- A second operator adapter for merchants mainly on other networks: MTN MoMo request-to-pay or the Orange Money merchant API, at the operator's own rate rather than an aggregator's.
- PI-SPI interoperable QR through a licensed partner, if it is live for merchants in Côte d'Ivoire: one QR for every wallet and bank, and the end of per-operator work.
- Onboarding and support playbook.
- Progressive verification workflow and fraud-review queue, only where the partner and regulator approve.

- **Layaway test** with 2–3 merchants whose goods suit it, never called credit ([BUSINESS-MODEL.md § Layaway test](BUSINESS-MODEL.md#layaway-test)).

**Exit gate:** merchants pay or renew; acquisition and support economics are known; the product works under low connectivity.

## Phase 3 — Digital tontine · *planned*

**Goal:** help existing community groups track contributions and schedules, respecting their existing rules.

- Closed groups, membership, turn order, fixed amounts, reminders.
- Contributions through the licensed payment provider, never through a Fidelia account.
- Idempotent webhooks, reconciliation and dispute workflow.
- Proof-of-regularity per completed cycle, visible to members.
- Tier 1 verification where required.
- Priority partner: an MFI serving women (e.g. Fin'ELLE).

**Does not begin** until the merchant product has validated willingness to pay and identity, audit logging, authorisation, consent, payment state and reconciliation are stable. The code foundation already exists and stays disabled until then.

**Measure:** active members after 90 days · % of cycles completed without incident · women's share of usage.

## Phase 4 — Explainable reliability indicator · *planned*

**Goal:** a transparent signal built from regular activity (purchase regularity, tontine cycles, savings regularity, seniority).

- Documented inputs and a user-visible explanation of what improves it.
- Correction and appeal workflow; bias and outcome monitoring (does not penalise small amounts).
- **Internal use first**, e.g. unlocking deferred payment at a partner merchant.
- No third-party sharing without consent and legal review; follow the BCEAO scoring and sandbox route.

## Phase 5 — Partner financial services · *planned*

**Goal:** connect eligible merchants and customers to licensed credit and savings partners.

- Written partner agreement; Tier 2 identity and consented data-sharing contract.
- **Merchant credit:** consented revenue-history export for working-capital, stock credit or revenue advance, optionally backed by a guarantee scheme (SGPME, GUDE-PME support).
- **Goal-based savings** (locked until date or amount), held by the licensed partner, with the holder named in the app.
- Funds-flow audit before launch; direct fund flow to the provider.
- Referral and outcome tracking; first commissions.
- Contextual financial education at key moments.

Fidelia remains a technology and distribution partner unless its regulatory status changes.

**Measure:** partnerships signed · merchants who obtained credit through their Fidelia history · savings volume held by partners and % of goals reached · commission revenue compared with subscription revenue · gender gap per feature.

## Phase 6 — Expansion · *later*

Each extension needs its own user research, payment and support adapters, partner validation and regulatory review. The platform is reused; commercial operations are localised.

- More Abidjan corridors, then other Ivorian cities and rural merchant networks (e.g. PAMF-CI, UNACOOPEC-CI).
- A second UEMOA country only after the unit-economics gate.
- Agriculture (cooperatives, Cofina, GIZ) and micro-insurance.
- Public-service assistance aligned with the "zero paper" strategy (opportunistic).

## Strategic horizon — federated identity trust layer

A long-term option, not an MVP commitment: provider-issued attestations, consent and purpose management, assurance-level mapping, privacy-preserving verification, revocation and audit, interoperability APIs for licensed institutions.

**Entry conditions:** proven Tier 0 and partner-managed Tier 1/2 flows; written governance and data-sharing agreements; review with ARTCI, BCEAO and licensed partners; a liability model for incorrect or fraudulent claims; independent security and privacy assessment.

## Roadmap governance

For every proposed feature, record: the user problem and evidence · expected business value · data collected and purpose · partner or regulatory dependency · security and authorisation impact · success metric · rollback or shutdown condition · **whether it needs a new merchant habit** (if so, reject unless there is no alternative).

## Related documents

[CONCEPT.md](CONCEPT.md) · [BUSINESS-MODEL.md](BUSINESS-MODEL.md) · [PARTNERS.md](PARTNERS.md) · [Technical guide](../technical/TECHNICAL-GUIDE.md)
