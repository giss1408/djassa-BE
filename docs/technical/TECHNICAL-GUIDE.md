# Fidelia Technical Guide

This document is the technical navigation page for the repository. It describes what each technical area owns and where to find the operational instructions.

## Current backend

The backend is a FastAPI service with:

- SQLAlchemy models and Alembic migrations.
- PostgreSQL as the target relational database.
- Redis and Celery for asynchronous work.
- Phone + SMS code sign-in with JWT access tokens and rotating refresh tokens.
- In-house error reporting from the apps and the site (`/api/client-events`).
- Webhook signature verification and idempotency handling.
- Prometheus metrics and OpenTelemetry instrumentation.

API surfaces, by client:

- **Merchant app** (`fidelia-App-retailer`): `/api/auth/*` (phone sign-in), `/api/merchant/sales` and `/api/merchant/sales/sync` (optional `customer_phone` earns the customer points; the first time a number is used it needs `customer_consent: true`, see [ARTCI.md](../Reglementation/ARTCI.md)), `/api/merchant/customers/loyalty` and `/redeem` (balance and reward at the counter, by phone), `/api/merchant/venue/location` (GET/PUT: the shop's position, from the phone's GPS in the shop, for customers' directions), merchant deals, stats and payment requests. Signed out, it offers a **demo** (`lib/features/demo/`): the real screens on a pretend shop, wired to an in-memory ledger and an in-app fake server, in a separate provider container; nothing is sent, and what is done in the demo is not counted in usage analytics (only `demo_started` is).
- **Customer app** (`fidelia-App-user`): opens without an account. Venues, categories, on-duty pharmacies and deals are **public** (no token needed, `PUBLIC_READ_RATE_LIMIT` per IP, default 120/minute; a token, when sent, adds the customer's own points to a shop page). Sign-in (`/api/auth/*`, phone + code) is asked only to pay (pay-code lookup, customer payments) or to see loyalty balance and redemption.
- **Admin**: pharmacy duty rotation, venue pay codes, featured deals, merchant accounts (`/api/admin/users/roles`), app error reports (`/api/admin/client-events`).
- **All apps and the site**: `POST /api/client-events` (error reports, no sign-in needed).
- **Foundations not exposed to users yet**: tontines, consents, identity verification tiers, exports, payments with refunds and disputes (see [ROADMAP.md § Where we stand](../business/ROADMAP.md#where-we-stand)).

Recorded sales (`Merchant`/`Transaction`) and customer payments (`Venue`/`CustomerPayment`/`LoyaltyEntry`) are currently separate models. Unifying them into one merchant event stream is a Phase 1 requirement.

The implementation is still a prototype. Authentication, resource authorization, financial workflows, and production configuration require further hardening before real financial use.

## Sign-in

`app/api/auth.py`. The phone number is the account (CONCEPT.md, Tier 0).

1. `POST /api/auth/otp/request {phone, app}` sends a 6-digit code. Only an HMAC
   is stored. Codes live 5 minutes and allow 5 guesses; a number gets one code
   per 60 s and 5 per hour; each IP 10 requests per minute.
2. `POST /api/auth/otp/verify {phone, code, app}` returns a 60-minute access
   token (JWT, `sub` = `tel:+225…`, the same key as counter loyalty, so counter
   points appear on first sign-in) and a 90-day refresh token (stored hashed).
   `app: "customer"` creates the account on first use. `app: "merchant"`
   requires the merchant role, granted with
   `POST /api/admin/users/roles {phone, role: "merchant", venue_id}`.
3. `POST /api/auth/refresh` rotates the pair. Replaying a used refresh token
   revokes that whole session (stolen-token detection).
   `POST /api/auth/logout` revokes it.

SMS delivery is `app/services/otp_sender.py`, chosen by `OTP_SENDER`:

| Variable | Meaning |
|---|---|
| `OTP_SENDER=console` | Default outside production. Logs the code. Refused when `FIDELIA_ENV=production`. |
| `OTP_DEV_ECHO=1` | With `console` only, returns the code in the API response so the apps fill it in. Local development only: anyone could sign in as any number. |
| `OTP_SENDER=africastalking` | SMS via Africa's Talking with `AT_USERNAME`, `AT_API_KEY`, optional `AT_SENDER_ID`, `AT_SANDBOX=1`. |

Sending SMS is the only part with a cost: a few cents per message, set by the
provider. The `OtpSentButNotVerified` alert watches for SMS pumping.

## Investor brief behind a password

The investor brief, the NDA and the letters of interest are served by the API
at `/brief/` (`app/api/investor_brief.py`), not by the public site, which is
static and cannot ask for a password. The files live in
`backend-api/app/investor_brief/`; the letters' PDFs are rebuilt from
`scripts/letters/` with `scripts/build-letters.sh` (needs Chrome).

| Variable | Meaning |
|---|---|
| `INVESTOR_BRIEF_PASSWORD` | The one shared password, at least 12 characters. Unset or shorter: the brief is closed (503). Changing it signs every reader out. |
| `FIDELIA_SITE_URL` | The public site's address, for the brief's "Website" link. Unset: the link is left out. |
| `INVESTOR_BRIEF_LOGIN_LIMIT` | Password attempts per address. Default `5/minute`. |

A reader who enters the password gets a signed, HttpOnly cookie valid for 7
days on `/brief` only. Pages are sent `no-store` and `noindex`. The site's
"Investor brief" button opens `<API>/brief/` when the site is built with
`VITE_FIDELIA_API_BASE`.

## Offer alerts and offer use at the counter

When a merchant publishes a deal, `app/services/push.py` sends one push to
the Firebase Cloud Messaging topics `offers_<commune>` and `venue_<id>`. The
customer app subscribes the phone to the commune the customer chose and to
their favourite shops, so Fidelia never stores who receives what. At most one
alert per shop per 24 hours; a sample shop or a deal starting later is not
announced. The outcome is stored on the deal (`notify_status`) and shown to the
merchant. The alert is sent after the response, in the API process, so it
needs no worker.

| Variable | Meaning |
|---|---|
| `PUSH_PROVIDER=console` | Default. Logs the alert; customers receive nothing. |
| `PUSH_PROVIDER=fcm` | Real pushes. Needs `FCM_PROJECT_ID` and `FCM_SERVICE_ACCOUNT_JSON` (Firebase console > Project settings > Service accounts > Generate new private key; paste the file's content). |

The customer app enables alerts only when built with the four `FIREBASE_*`
defines (`fidelia-App-user/lib/core/config/env.dart`), taken from the same
Firebase project's Android app.

A customer who comes to the counter with a deal is recorded by the merchant
or cashier with **Client venu** in the merchant app
(`POST /api/merchant/deals/{id}/uses`), answering only whether the customer is
new. No customer data is stored. `GET /api/merchant/deals/uses/summary` gives
the week's count, the "new customers brought by Fidelia" figure of the pilot
([KPI.md](../business/KPI.md)).

Locally, with sample data seeded, `07 00 00 00 02` is a merchant that runs
*Chez Tantie Awa*. Any other number signs in to the customer app.

The username/password `POST /api/token` with the `demo`/`client`/`admin`
accounts remains for development and tests. It answers 404 when
`FIDELIA_ENV=production` or `FIDELIA_DEMO_LOGIN=0`. Until a production admin
signs in by phone, grant the first admin role directly in the database
(`UPDATE users SET roles = 'admin' WHERE phone_e164 = '+225…'`).

## Merchant onboarding

`app/api/onboarding.py`. There are two ways in, and both end with a shop, a merchant login and a QR:

| Who starts | Path |
|---|---|
| An agent or admin | `POST /api/admin/venues {category, name, commune, address, payout_provider, payout_account, merchant_phone, points_per_100…}` creates the shop, makes `merchant_phone` its Fidelia Pro login, and issues the payment QR when a wallet is given. |
| The merchant, from the Fidelia Pro sign-in screen (*Inscrire mon commerce*) | `POST /api/partner-requests/code` proves the phone. `POST /api/partner-requests` files the shop details. An admin lists them at `GET /api/admin/partner-requests`, calls the merchant, then calls `/approve` (with corrections) or `/reject`. Approving runs the same creation as above. The merchant is told by SMS. |

One phone number runs one shop (409 otherwise), because Fidelia Pro finds "my shop" from the token. After sign-in the merchant sets the shop position from their phone, and connects Wave (points only by default). See [DEPLOY-TEST.md § 6](DEPLOY-TEST.md).

## Shop photos and videos

`app/api/media.py`. Each shop has up to **10 photos and 3 videos of 60 s**. Merchants add them in Fidelia Pro (*Photos et vidéos*) and admins in fidelia-installer; customers see them on the shop page (`media` in `GET /api/venues/{id}`).

Uploads are never served as sent (`app/services/media_processing.py`):

| | Kept | Typical size |
|---|---|---|
| Photo | WebP at 320, 720 and 1280 px wide; orientation fixed; **all metadata stripped** (GPS, phone model) | thumb ~10–20 KB, 720 px ~40–70 KB |
| Video | H.264 Main + AAC mono, short side ≤ 480 px, ≤ 600 kbit/s, `faststart`, metadata stripped; plus a 720 px WebP poster | ~4.5 MB a minute |

A photo is processed during the upload request and returns `ready`. A video returns `processing` and is converted after the response, in the API process, one video at a time (`MEDIA_VIDEO_JOBS`). ffmpeg is the system's when installed (the Docker image has it), or else the static build inside the `imageio-ffmpeg` wheel. The wheel is what runs on Render's native Python runtime, where nothing can be apt-installed; `FFMPEG_BINARY` overrides both. On Render's free instance (512 MB, a fraction of a CPU) a 60 s clip takes a few minutes; the list shows `ready`, or `failed` with the reason (too long, unreadable). The apps load only thumbnails by default. A video shows its length and size, and downloads only when tapped; the customer app then streams it in its own player. List endpoints (`GET /api/venues`, on-duty pharmacies) carry `cover_url`, the first photo's 320 px thumbnail, for the cards; the shop page uses the 720 px photo as its header. The merchant app also shrinks photos on the phone before upload (1600 px, JPEG 80).

Storage (`app/services/media_storage.py`), chosen by `MEDIA_STORAGE`:

| Value | Use |
|---|---|
| `local` (default) | Development: files under `MEDIA_LOCAL_DIR` (default `./media`), served by the API at `/media/…`. Refused in production; Render's free disk is wiped on deploy. |
| `r2` | Cloudflare R2: free up to 10 GB, **no bandwidth fees**. Set `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` (an R2 API token limited to the bucket), `R2_BUCKET`, and `MEDIA_PUBLIC_BASE_URL` (the bucket's public `r2.dev` URL or a custom domain). |

R2 setup: Cloudflare dashboard → R2 → create bucket `fidelia-media` → Settings → enable public access (r2.dev) or connect a custom domain such as `media.fidelia.ci`. Then R2 → Manage API tokens → *Object Read & Write* on that bucket only. Keys contain a random part and files never change, so they are served with a one-year immutable cache. Deleting a media item deletes its files.

## Admin screen

`../fidelia-installer`, a React static site for the Fidelia team: shops and their media, sign-up requests, account recoveries, users and roles, and app errors. Admins sign in with phone + SMS code using `app: "admin"`; only numbers with the admin role get a session. The supporting endpoints are `GET/PATCH /api/admin/venues[/{id}]`, `GET /api/admin/users?phone=`, `POST /api/admin/users/disable` and `POST /api/admin/users/roles/revoke`. An admin cannot suspend themselves or remove their own admin role. Add the site's origin to `CORS_ORIGINS`.

## Account recovery

`app/api/account.py`. In the apps: *Mon compte* in the menu, and *Numéro perdu ?*
on the sign-in screen.

| Situation | Path |
|---|---|
| Phone lost or stolen, same number (replacement SIM) | Sign in again, then *Déconnecter les autres téléphones*: `POST /api/auth/sessions/revoke-others` ends every other session. Admins can do it for a number with `POST /api/admin/users/revoke-sessions`. |
| New number, old SIM still works | `POST /api/auth/change-number/request` sends a code to each number. `/confirm` with both codes moves the account at once. A signed-in session alone is not enough, because a phone left unlocked must not be able to give the account away. |
| Old number lost | `POST /api/auth/recovery/code` proves the new number. `POST /api/auth/recovery` files a request with the old number and details, and the old number is warned by SMS. An admin reviews it at `GET /api/admin/recovery-requests`, which shows roles, shops, loyalty venues and last payment to ask the caller about. The admin then calls `/approve` or `/reject`, and the new number is told by SMS. |

A move (`app/services/account_move.py`) re-keys every column that belongs to
the person (points, payments, shop, tontines, consents, identity) from the old
`tel:` key to the new one. It leaves audit columns (who exported, recorded or
connected something) as history, ends every session, and logs the change in
`account_number_changes`. A number that already has an account is refused:
two accounts are never merged automatically. `tests/test_account_recovery.py`
fails if a new account-key column is added without being classified.

Codes carry a purpose (`sign_in`, `change_number`, `recovery`) and only work
for it. Access tokens already issued stay valid until they expire (at most
60 minutes) and then cannot be renewed.

## App error monitoring

The apps and the site report their own uncaught errors to
`POST /api/client-events` (`app/api/client_events.py`). There is no third-party
SDK. Reports are batched on the device and sent at start-up or when the app
returns to the foreground, never on a timer. Digit runs in messages and tokens
are scrubbed on the device and again on the server. Each report increments
`fidelia_client_events_total{app, platform, kind, app_version}`. The
*Fidelia apps and sign-in* Grafana dashboard and the `AppErrorSpike` and
`AppCrashAfterRelease` alerts read that counter. Admins read grouped stacks
with `GET /api/admin/client-events?app=user&days=7`. Release builds are
obfuscated: symbolize a stack with `flutter symbolize` and the symbols that
`scripts/build-release.sh` archived for that version. Native (Java/engine)
crashes are not covered; use Play Console's Android vitals for those.

## App usage analytics (pilot)

Our own pipeline again, no analytics SDK: merchants and customers pay per
byte, and nothing goes to a third party. Both apps keep a small aggregated
queue (`lib/core/monitoring/usage_tracker.dart`) and send it to
`POST /api/usage-events` (`app/api/usage_events.py`) in one request at
start-up or when the app returns to the foreground, never on a timer.

* **Identity.** Every event carries an *install id*: random, created on
  first launch, kept in the app's storage (not a device id, not a phone
  number). It counts installs and active users. The merchant app's events
  are tied to the shop (`venue_id`, from the token) because the pilot is
  measured per merchant; the customer app's events are **never** tied to an
  account, even when the customer is signed in.
* **What is sent.** Allow-listed event names only (`EVENT_NAMES`), at most 8
  short props, digit runs scrubbed. Merchant app: `app_open`, `screen_view`,
  `sale_form_opened`, `sale_recorded` (seconds taken), `sale_abandoned`
  (step), `daily_report` (the W4-3 end-of-day estimate), `data_used`.
  Customer app: `app_open`, `tab_view`, `screen_view`, `venue_viewed`,
  `deal_opened`, `media_viewed`, `scan_opened`, `payment_started`,
  `payment_completed`, `data_used`.
* **Where to read it.** The *Fidelia pilot usage* Grafana dashboard
  (Prometheus totals) and `GET /api/admin/usage?app=retailer|user&days=30`
  for installs, active installs, screens, venues and deals seen, and per
  merchant: active days, median seconds to record a sale, abandons, data
  used per day and the **recorded share** (sales the server holds ÷ the
  merchant's own estimate), the pilot's master metric.
* **Not here, on purpose.** How long sales waited offline is already in
  `sale_events` (`recorded_at` − `occurred_at`). Native crashes: Play
  Console's Android vitals.
* **Retention.** `USAGE_EVENTS_RETENTION_DAYS` (default 400), purged by
  `app/services/purge.py`.

## Repository map

| Area | Location | Purpose |
|---|---|---|
| Backend API | [backend-api](../../backend-api/) | FastAPI application, models, routes, workers, tests |
| Merchant app | [fidelia-App-retailer](../../../fidelia-App-retailer/ARCHITECTURE.md) | Flutter, offline-first sale recording |
| Customer app | [fidelia-App-user](../../../fidelia-App-user/) | Flutter, discovery, QR payment, loyalty |
| Public site | [fidelia-Web](../../../fidelia-Web/README.md) | React/Vite investor and partner site |
| Product concept | [CONCEPT.md](../business/CONCEPT.md) | What Fidelia is, the four products, boundaries |
| Business model | [BUSINESS-MODEL.md](../business/BUSINESS-MODEL.md) | Customers, revenue, unit economics, boundaries |
| Partner strategy | [PARTNERS.md](../business/PARTNERS.md) | Institutions, outreach, pilot questions |
| Product roadmap | [ROADMAP.md](../business/ROADMAP.md) | Current state, phases, exit criteria |
| Architecture | [Architecture/README.md](../../Architecture/README.md) | Canonical architecture index and deployment modes |
| Security | [Architecture/SECURITY.md](../../Architecture/SECURITY.md) | Application and financial-security principles |
| Container security | [Architecture/security-architecture.md](../../Architecture/security-architecture.md) | Compose/Kubernetes hardening |
| VPS test deployment | [VPS-TEST-SERVER.md](VPS-TEST-SERVER.md) | Test-server setup and automated deployment |
| Production and monitoring | [PRODUCTION.md](PRODUCTION.md) | Production deploy, settings, metrics, alerts and runbooks |
| Database migrations | [backend-api/MIGRATIONS.md](../../backend-api/MIGRATIONS.md) | Schema changes, rollback, and deployment rules |
| Contributions | [CONTRIBUTING.md](../../CONTRIBUTING.md) | Branches, tests, and security checklist |
| Contributor guidance | [skills](../../skills/) | Implementation and writing guidance |
| Jenkins CI/CD | [Jenkinsfile](../../Jenkinsfile) | Validation, image supply-chain checks, publishing, and gated deployment |

## Local development

From `backend-api`:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
docker compose -f docker-compose.dev.yml up -d db redis
export DATABASE_URL=postgresql+asyncpg://fidelia:fidelia@127.0.0.1:5432/fidelia
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run tests with:

```bash
pytest -q
```

Schema changes follow [MIGRATIONS.md](../../backend-api/MIGRATIONS.md). Apply migrations explicitly before starting a new deployment.

Run the worker in a second terminal:

```bash
export CELERY_BROKER_URL=redis://127.0.0.1:6379/0
celery -A app.celery_app.celery_app worker --loglevel=info
```

## Low-connectivity synchronization

Clients should treat connectivity loss as normal. Queue transaction operations locally and assign each operation a stable, random `idempotency_key` of at least 8 characters. Retry the batch after reconnecting:

```http
POST /api/transactions/sync
Authorization: Bearer TOKEN
Content-Type: application/json
```

```json
{
	"operations": [
		{
			"idempotency_key": "device-20260921-0001",
			"merchant_id": 42,
			"amount": "12.50",
			"currency": "XOF",
			"type": "sale"
		}
	]
}
```

The batch is limited to 50 operations. Each result is independently classified as `accepted`, `already_processed`, or `rejected`. The same key with a different payload is rejected. Clients should retain rejected operations for user review and remove accepted or already-processed operations from the local queue.

For a single write, send the same key as the `Idempotency-Key` header on `POST /api/transactions`. Never generate a new key when retrying the same operation.

## Country and support configuration

Clients should load country capabilities instead of embedding country rules in the app:

```http
GET /api/config/countries/CI
```

The response describes the country currency, phone prefixes, supported languages, support channels, and payment-provider adapter names. The initial profiles cover Côte d'Ivoire (`CI`), Ghana (`GH`), Nigeria (`NG`), and Kenya (`KE`). Provider names are configuration identifiers; credentials and production integrations are still deployment-specific.

Authenticated users can open a localized support request:

```http
POST /api/support/requests
```

The request includes `country_code`, `language`, `channel`, `category`, and `message`. The API validates that the selected language and channel are available for the selected country and stores the language/channel metadata so an operator or future SMS/WhatsApp adapter can route it correctly. The current confirmation catalog contains English and French; unsupported translations fall back to English while preserving the requested language for support handling.

Identity verification is progressive: Tier 0 supports low-friction loyalty with a phone or operator-linked identifier; higher-risk tontine, savings, and credit workflows must request stronger partner-approved verification. The backend should store verification outcomes and provenance rather than raw biometric material whenever possible.

The current identity API is:

- `POST /api/identity/profile`: creates a Tier 0 profile after country and E.164 phone-prefix validation.
- `GET /api/identity/me`: returns the authenticated user's verification metadata.
- `POST /api/identity/verification/1` or `/2`: records a provider-required request; it does not self-approve a higher tier.

Tier 1 and Tier 2 completion require a future licensed identity/KYC adapter or operator attestation path. The demo authentication system is not a production identity provider.

The strategic identity architecture is federated rather than centralized: Fidelia should exchange scoped, provider-issued attestations and consent records, not copy raw operator KYC, biometric, or national-ID databases. Each claim should include its issuer, assurance level, purpose, issue time, expiry/revocation status, and audit reference. The original operator or licensed KYC institution remains authoritative for the underlying verification.

## GraphQL

GraphQL is available at `POST /graphql` as a complementary API surface. It currently exposes public country capability queries, authenticated `myTransactions` queries, and authenticated `syncTransactions` mutations with the same 50-operation limit and idempotency behavior as REST.

Use REST for provider webhooks and operational integrations. GraphQL resolvers must preserve the same ownership, pagination, payload-size, and Decimal-money rules. Do not add unrestricted transaction queries or expose secrets through the schema. In production, place GraphQL behind the gateway and review introspection, query-depth, and rate-limit settings.

## Payment orchestration

Fidelia now models payment intents without pretending that the sandbox moves real money:

```text
created -> pending -> succeeded
					-> failed
					-> disputed
succeeded -> refund_pending -> refunded
```

`POST /api/payments` validates the country/currency pair, creates an idempotent payment intent, calls the configured provider adapter with a timeout, and stores the provider's external transaction ID. `GET /api/payments/{id}` returns the owner-scoped state. Refunds and disputes have separate endpoints and persisted records.

The default `PAYMENT_PROVIDER=sandbox` adapter is safe for tests and returns pending sandbox references. A live provider must implement the adapter contract in `app/services/payment_providers.py`, receive credentials from a secret manager through `PAYMENT_PROVIDER_API_KEY`, and provide signed callbacks and settlement reports.

Provider callbacks must include an external ID, status, amount, and currency. The webhook path verifies the signature and replay window, then records a reconciliation row only when amount and currency match the payment intent. A valid signature alone never settles money.

### Customer payments to a venue: Wave, merchant's own account (pilot)

During the pilot Fidelia has no Wave account and never holds funds. Each merchant connects **their own** Wave Business account (`app/api/wave.py`):

| Endpoint | Who | What |
|---|---|---|
| `PUT /api/merchant/wave` | merchant | Creates or updates the connection; only the fields sent change. An empty body creates the `webhook_url` to paste into the Wave portal. `webhook_secret` alone is enough for points (points only, the default). `api_key` (Checkout access only) is optional and enables in-app payment. It is tested first with a search that moves no money. Secrets are sealed with Fernet under `FIDELIA_ENCRYPTION_KEY` (`app/core/secretbox.py`) and never returned; only a hint (`…a1B2`) is. `payments_enabled` says whether a key is connected. |
| `GET` / `DELETE /api/merchant/wave` | merchant | Status (key hint, webhook configured, last event) / disconnect. |
| `POST /webhooks/wave/{token}` | Wave | Signed events (`Wave-Signature`, HMAC-SHA256, 5-minute replay window). The random token identifies the venue. |
| `GET /api/customer/payments/{id}` | customer | Re-reads a pending checkout from Wave, so a late webhook does not block the app. |

Flow: the customer pays with Wave → `POST /api/customer/payments` creates a Wave checkout **with the merchant's key** (amount fixed, payer restricted to the customer's number, `client_reference` = the payment's idempotency key) → the response is `pending` with `checkout_url` → the app opens it, the Wave app approves → `checkout.session.completed` settles the payment, grants points and writes one confirmed `sale_event`.

`merchant.payment_received` (someone paid the merchant's ordinary Wave QR, outside Fidelia) records a confirmed sale keyed `wave:<transaction id>`, and grants the venue's points on the sender's phone number (`tel:+225…`, the counter key) **only if that number has a loyalty consent on file** (`loyalty_consents`, given at sign-in in the customer app or at a counter). Without one the sale is recorded anonymously and the number is not stored ([ARTCI.md](../Reglementation/ARTCI.md)). It is skipped when the same money is a Fidelia checkout (same transaction id, or a pending checkout from the same number for the same amount).

A points-only venue (no key) gets no checkout: in production a Wave payment in the app is refused with "Payez avec le QR Wave du commerce", and the payment to the shop's own QR still earns the points through `merchant.payment_received`.

`MOBILE_MONEY_PROVIDER=wave`: venues with a connected key use Wave for Wave payments; other payments stay simulated in test and are refused (422, "payez au comptoir") in production. Wave has no sandbox: tests use a mock transport (`tests/test_wave.py`); the first live check is a small real payment.

## VPS test deployment

Use the automated deployment script, not the development server:

```bash
cd backend-api
./deploy-vps-test.sh
```

The script builds the image, creates test-only secrets, starts dependencies, applies migrations, starts the API and worker, and verifies health. See [VPS-TEST-SERVER.md](VPS-TEST-SERVER.md) for prerequisites and access controls.

## Configuration contract

Required production-like variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection URL |
| `FIDELIA_SECRET_KEY` | JWT signing key; never use a placeholder |
| `MOBILE_MONEY_SECRETS` | Comma-separated webhook signing keys |
| `FIDELIA_ENCRYPTION_KEY` | Seals merchants' Wave keys at rest; changing it forces merchants to reconnect |
| `MEDIA_STORAGE=r2` + `R2_*`, `MEDIA_PUBLIC_BASE_URL` | Shop photos and videos (see Shop photos and videos) |
| `OTP_SENDER` + provider keys | Sign-in codes by SMS (see Sign-in) |
| `PUSH_PROVIDER=fcm` + `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON` | Offer alerts to the customer app (see Offer alerts) |
| `INVESTOR_BRIEF_PASSWORD`, `FIDELIA_SITE_URL` | The investor brief at `/brief/` (see Investor brief) |
| `CELERY_BROKER_URL` | Redis broker URL |

Do not use the demo credentials or placeholder secrets on an Internet-accessible server.

## Technical decision rules

- Use migrations for schema changes; do not rely on `create_all` for production rollout.
- Derive ownership from the authenticated identity, never from an untrusted request body.
- Protect every export and financial read with explicit authorization.
- Treat payment webhooks as untrusted input; verify signatures, timestamps, and idempotency.
- Keep PostgreSQL, Redis, metrics, and internal worker endpoints private.
- Add tests for unauthorized access and cross-user data isolation with every sensitive endpoint.

## Before production

The following remain mandatory work:

- Configure a real `OTP_SENDER` (and a funded SMS account) and set `FIDELIA_ENV=production`, which disables the demo login and the console sender.
- Implement resource authorization beyond roles.
- Remove default secrets and fail closed at startup.
- Schedule `maintenance.purge_expired` daily (see `backend-api/README-CELERY.md`).
- Complete payment reconciliation and financial state transitions.
- Add backup and restore procedures.
- Enforce immutable image versions and blocking vulnerability scans.
- Review regulatory responsibilities with qualified local counsel and licensed partners.
