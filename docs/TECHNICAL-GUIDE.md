# Djassa Technical Guide

This document is the technical navigation page for the repository. It describes what each technical area owns and where to find the operational instructions.

## Current backend

The backend is a FastAPI service with:

- SQLAlchemy models and Alembic migrations.
- PostgreSQL as the target relational database.
- Redis and Celery for asynchronous work.
- JWT-based authentication in the current skeleton.
- Webhook signature verification and idempotency handling.
- Prometheus metrics and OpenTelemetry instrumentation.

The implementation is still a prototype. Authentication, resource authorization, financial workflows, and production configuration require further hardening before real financial use.

## Repository map

| Area | Location | Purpose |
|---|---|---|
| Backend API | [backend-api](../backend-api/) | FastAPI application, models, routes, workers, tests |
| Product concept | [PRODUCT-CONCEPT.md](PRODUCT-CONCEPT.md) | User problem, product boundary, value proposition |
| Business model | [BUSINESS-MODEL.md](BUSINESS-MODEL.md) | Customers, revenue, unit economics, boundaries |
| Partner strategy | [PARTNERS-AND-OUTREACH.md](PARTNERS-AND-OUTREACH.md) | Institutions, outreach, pilot questions |
| Product roadmap | [ROADMAP.md](ROADMAP.md) | Phases, dependencies, exit criteria |
| Architecture | [Architecture/README.md](../Architecture/README.md) | Canonical architecture index and deployment modes |
| Security | [Architecture/SECURITY.md](../Architecture/SECURITY.md) | Application and financial-security principles |
| Container security | [Architecture/security-architecture.md](../Architecture/security-architecture.md) | Compose/Kubernetes hardening |
| VPS test deployment | [VPS-TEST-SERVER.md](VPS-TEST-SERVER.md) | Test-server setup and automated deployment |
| Database migrations | [backend-api/MIGRATIONS.md](../backend-api/MIGRATIONS.md) | Schema changes, rollback, and deployment rules |
| Contributions | [CONTRIBUTING.md](../CONTRIBUTING.md) | Branches, tests, and security checklist |
| Contributor guidance | [skills](../skills/) | Implementation and writing guidance |
| Jenkins CI/CD | [Jenkinsfile](../Jenkinsfile) | Validation, image supply-chain checks, publishing, and gated deployment |

## Local development

From `backend-api`:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
docker compose -f docker-compose.dev.yml up -d db redis
export DATABASE_URL=postgresql+asyncpg://djassa:djassa@127.0.0.1:5432/djassa
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run tests with:

```bash
pytest -q
```

Schema changes follow [MIGRATIONS.md](../backend-api/MIGRATIONS.md). Apply migrations explicitly before starting a new deployment.

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

The strategic identity architecture is federated rather than centralized: Djassa should exchange scoped, provider-issued attestations and consent records, not copy raw operator KYC, biometric, or national-ID databases. Each claim should include its issuer, assurance level, purpose, issue time, expiry/revocation status, and audit reference. The original operator or licensed KYC institution remains authoritative for the underlying verification.

## GraphQL

GraphQL is available at `POST /graphql` as a complementary API surface. It currently exposes public country capability queries, authenticated `myTransactions` queries, and authenticated `syncTransactions` mutations with the same 50-operation limit and idempotency behavior as REST.

Use REST for provider webhooks and operational integrations. GraphQL resolvers must preserve the same ownership, pagination, payload-size, and Decimal-money rules. Do not add unrestricted transaction queries or expose secrets through the schema. In production, place GraphQL behind the gateway and review introspection, query-depth, and rate-limit settings.

## Payment orchestration

Djassa now models payment intents without pretending that the sandbox moves real money:

```text
created -> pending -> succeeded
					-> failed
					-> disputed
succeeded -> refund_pending -> refunded
```

`POST /api/payments` validates the country/currency pair, creates an idempotent payment intent, calls the configured provider adapter with a timeout, and stores the provider's external transaction ID. `GET /api/payments/{id}` returns the owner-scoped state. Refunds and disputes have separate endpoints and persisted records.

The default `PAYMENT_PROVIDER=sandbox` adapter is safe for tests and returns pending sandbox references. A live provider must implement the adapter contract in `app/services/payment_providers.py`, receive credentials from a secret manager through `PAYMENT_PROVIDER_API_KEY`, and provide signed callbacks and settlement reports.

Provider callbacks must include an external ID, status, amount, and currency. The webhook path verifies the signature and replay window, then records a reconciliation row only when amount and currency match the payment intent. A valid signature alone never settles money.

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
| `DJASSA_SECRET_KEY` | JWT signing key; never use a placeholder |
| `MOBILE_MONEY_SECRETS` | Comma-separated webhook signing keys |
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

- Replace demo authentication with a real identity and user store.
- Implement role and resource authorization.
- Remove default secrets and fail closed at startup.
- Add refresh-token or session revocation strategy.
- Complete payment reconciliation and financial state transitions.
- Add backup and restore procedures.
- Enforce immutable image versions and blocking vulnerability scans.
- Review regulatory responsibilities with qualified local counsel and licensed partners.
