# Changelog — Fidelia backend (API, docs, deployment)

What the backend can do, newest first. It has no version numbers yet: the
test environment deploys `integration`, production deploys `trunk`. Entries
are grouped by the day the work landed. The product was called **Djassa**
until 6 October 2026, then **Hossouko**, and is **Fidelia** since 9 October.

## 2026-10-24

- **Super admin** (`app/services/super_admin.py`): `FIDELIA_SUPER_ADMIN_PHONE`
  and `FIDELIA_SUPER_ADMIN_PASSWORD` (Render secrets) give one number the
  `admin` and `superadmin` roles and a verified password on every start, so
  Fidelia Admin is never locked out. Other admins cannot suspend, sign out or
  reset it.
- **Test logins' password from Fidelia Admin**: `GET
  /api/admin/accounts/test-accounts` and `PUT .../test-accounts/password`
  (super admin only, 404 in production) set one password on the shared test
  numbers, which `FIDELIA_SEED_PASSWORD` only seeds.
- **Store review login** (`app/services/review_account.py`): with
  `STORE_REVIEW_PHONE` and `STORE_REVIEW_PASSWORD` set (Render secrets), every
  start gives that number a password, a verified number and the customer and
  merchant roles, so Apple and Google reviewers sign in to both apps without a
  WhatsApp code. It runs its own sample shop, with no wallet and kept out of
  `/api/venues` and `/api/deals`. Allowed in production; half a setup or a
  weak password stops the start.

## 2026-10-22

- **Password sign-in** (`app/api/password_auth.py`): `POST /api/auth/register`,
  `/login`, `/verify-number`, `/number`, `/password-reset`, `/password` replace
  the SMS codes. Passwords are argon2id (8 to 128 characters, not only
  digits); five wrong ones lock a number for 15 minutes. Access tokens carry
  `vf` and `pc`: an unverified number gets `403 number_not_verified` and a
  temporary password `403 password_change_required` everywhere else.
- **WhatsApp number checks** (`account_checks`, `app/services/whatsapp.py`):
  the team sends each code by hand through a `wa.me` link (24 h, 5 attempts).
  Change of number and lost-number recovery use the same checks; logins
  created by the team or a shop owner wait for a temporary password.
- **Admin accounts API**: `/api/admin/accounts` (checks, send, refuse, user
  search, suspend, restore, sign out, reset password) for the Fidelia Admin
  app; every call is logged in `admin_actions`.
- **SMS removed**: `/api/auth/otp/*` answer 410 ("Mettez a jour
  l'application"); the Orange SMS integration, `OTP_SENDER`, `OTP_DEV_ECHO`
  and `TEST_OTP_NUMBERS` are gone.
- **Seed passwords**: the shared test numbers sign in with the password in `FIDELIA_SEED_PASSWORD` (a Render secret; unset = no password)
  (refused when `FIDELIA_ENV=production`).
- **First admin**: `python -m app.scripts.set_password +225...` sets a
  verified password on an existing number.
- Cloudflare rate limit now covers `POST` login, register and password-reset
  (`login_rate_limit`, was `otp_rate_limit`).
- Migrations `0029_password_signin`, `0030_drop_otp_challenges`.

## 2026-10-12

- **Pilot record and scorecard** (`app/api/pilot.py`): `GET/PUT
  /api/admin/venues/{id}/pilot` holds what the team records by hand on a
  pilot merchant: the pre-Fidelia baseline (tickets, basket, mobile-money
  share, repeat-customer estimate), dated by the server so a baseline taken
  after the first sale is flagged; the owner's self-declared gender (optional,
  cleared when the shop changes owner); and the day-45 answer to the paid-plan
  offer (a commitment names its plan and price; nothing is billed during the
  pilot). `GET /api/admin/pilot/scorecard` lists every pilot merchant with
  recorded share, repeat visits against the baseline, new customers from
  offers and commitment, each rate with its counts (docs: KPI.md § 3.5).
- The recorded-share formula is shared by the usage summary and the
  scorecard (`usage_events.recorded_share`).
- Migration `0028_pilot_merchants`.

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
- **Free `pilot` plan**: includes the signed revenue statement and long
  history, so pilot merchants can share a statement with a partner MFI.
  Set by an admin with amount 0; any price is refused (422), so it is never
  invoiced or counted in MRR.
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
