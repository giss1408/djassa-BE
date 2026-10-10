# Changelog — Fidelia backend (API, docs, deployment)

What the backend can do, newest first. It has no version numbers yet: the
test environment deploys `integration`, production deploys `trunk`. Entries
are grouped by the day the work landed. The product was called **Djassa**
until 6 October 2026, then **Hossouko**, and is **Fidelia** since 9 October.

## 2026-10-10

- **Offer alerts**: publishing a deal sends one push to the Firebase topics of
  the shop's commune and of the shop (`app/services/push.py`), at most once
  per shop per 24 hours, never for sample shops or deals starting later. The
  outcome is on the deal (`alert_status`). `PUSH_PROVIDER=console` by default;
  `fcm` with `FCM_PROJECT_ID` and `FCM_SERVICE_ACCOUNT_JSON` sends real pushes.
- **Offer use at the counter**: `POST /api/merchant/deals/{id}/uses` records a
  customer who came with a deal and whether they are new (idempotent, live
  deals of the caller's own shop only, owner or cashier); no customer data is
  stored. `GET /api/merchant/deals/uses/summary` gives the week's count.
- Migration `0027_deal_alerts_and_uses`.
- **Investor brief behind a password**: the brief, the NDA and the letters of
  interest (PDF) moved from the public site to the API at `/brief/`, opened
  with one shared password (`INVESTOR_BRIEF_PASSWORD`, 12+ characters; unset =
  closed). Signed 7-day cookie, rate-limited attempts, `no-store`/`noindex`.
  Letter PDFs are rebuilt with `scripts/build-letters.sh`.
- **Pilot boundaries** in the business docs: maquis and grocery shops, the
  customer app with a focused scope, everything free during the pilot.
- **Fin'ELLE pilot proposal** (`docs/business/PROPOSITION-PILOTE-FINELLE.fr.md`,
  French): MFI as a partner and acquisition channel before a payer.
- **Investor readiness** (`docs/business/INVESTOR-READINESS.md`, French in
  `INVESTOR-READINESS.fr.md`): the gaps
  investors will find, the rewritten story, market sizing, forecast
  assumptions, competitor table and next steps.
- **Investor brief rewritten** for investors (`/brief/`, EN and FR, and
  `INVESTOR-BRIEF.md` / `.fr.md`): one-sentence story, the product by day 1,
  week 1 and month 3, honest traction (built vs. expected from Phase 0),
  market sizing, competition, a three-year forecast with its assumptions,
  team needs, how investors get a return, and risks. Terms unchanged.
- **Roadmap status** brought up to date: phone/SMS-code sign-in and automatic
  Wave capture are built (prototype); gaps 1 and 7 say what remains.
- **Funders for Fidelia** in `docs/business/PARTNERS.md`: grants and public
  programmes, pre-seed investors, accelerators and later-phase funders, with
  their status as checked on 10 October 2026.

## 2026-10-09

- **Account deletion** (Google Play requirement): a customer deletes their
  account at once (`DELETE /api/account`): number, points, consent and
  sessions erased; payments and sales stay in the shops' records under an
  anonymous key. Merchants, cashiers and field agents send a request
  (`POST /api/account/deletion-request`) that an admin completes once the
  person owns no shop (`/api/admin/deletion-requests`). Migration 0026.
- **Acceptance tests** in plain language (Gherkin, `tests/acceptance/`):
  joining, points and rewards, consent, layaway, revenue statement, deletion.
- **Renamed to Fidelia**: `FIDELIA_*` settings, with the old `HOSSOUKO_*` and
  `DJASSA_*` names still accepted; payment QRs read `fidelia://pay/…`.
- **Deployment**: the test environment follows `integration`, production
  follows `trunk`; CI runs on both.
- **Google Play guide** (`docs/technical/PLAY-STORE.md`, `PLAY-RELEASE.md`).
- Contact address `contact.fidelia@regisse.com`.

## 2026-10-06

- **Loyalty consent** (ARTCI option 1): no points tied to a phone number
  without the customer's consent, given in the app or at the counter;
  withdrawing it erases the points.
- **Layaway** ("payer en plusieurs fois"), switched on per shop by an admin:
  one named good, a fixed price and an end date, payments recorded, one sale
  on handover; never credit (migration 0025).
- **Public catalogue**: shops, pharmacies and deals readable without an account.
- **Deal corner banners**; **Restaurant** category apart from maquis;
  **WhatsApp help** link (merchants always, customers from 100 points).
- KPI scorecard and ARTCI regulation notes in the business docs.
- Renamed to Hossouko, accepting the old `DJASSA_*` settings.

## 2026-10-04

- **Shared test numbers** that sign in with a fixed code (test environment).
- **Cashiers and field agents**: owners add cashiers; agents enrol shops on
  site; the admin approval checklist for new merchants.
- **Production readiness**: `render.production.yaml`, metrics behind a token,
  route labels, structured access logs, a daily SMS budget, Grafana Cloud
  alerts, dashboards and runbooks.

## 2026-10-02

- **Phone sign-in by SMS code** (OTP), sessions with rotating refresh tokens,
  number change and account recovery reviewed by an admin.
- **Merchant onboarding**: partner requests from the app, approved by an admin.
- **Shop photos and videos** (local disk or Cloudflare R2).
- **Error reports and pilot usage figures** from the apps
  (`/api/client-events`, `/api/usage-events`, `/api/admin/usage`).

## 2026-09-30

- **Points on cash sales** by the customer's phone number, and rewards handed
  over at the counter.
- **Operator-neutral payments**, starting with Wave; **merchants connect their
  own Wave Business account** (Checkout access only), so money goes straight
  to them.
- **Shop position** from the phone's GPS; the shop's **fixed payment QR**.
- **Test deployment** on Render's free plan with Neon Postgres.
- Investor brief (EN/FR), docs reorganised into business and technical.

## 2026-09-29

- **One sale stream** for every way of selling, each sale labelled with its
  evidence (confirmed by the payment provider or declared by the merchant).
- **Signed revenue statement** a partner can verify.
- Revenue made recordable; export authorisation fixed.

## 2026-09-27

- **Customer API**: shops, on-duty pharmacies, QR payments, loyalty.
- **Categories and deals** ("bons plans").
- CI builds, scans and tests without registry secrets.

## 2026-09-19 to 2026-09-21

- First version: FastAPI service with payments, transactions, tontines,
  identity assurance, Prometheus/Grafana monitoring, OpenTelemetry, security
  scans (Trivy), CI/CD and deployment scripts.
