# Skill: Implementation — Backend

Purpose: implement, test, and document backend services for `djassa` with an emphasis on clarity, security, and reproducibility.

When to use:
- Building FastAPI routes, GraphQL resolvers, authentication, authorization, PostgreSQL persistence, Alembic migrations, Celery jobs, country adapters, or support workflows.

Repository stack:
- Python 3.11 and FastAPI.
- SQLAlchemy async engine with PostgreSQL as the deployment database.
- Alembic for every schema change.
- Redis and Celery for asynchronous work.
- Pydantic schemas with bounded validation and `Decimal` for money.
- Pytest and HTTPX ASGI transport for API tests.

Key deliverables:
- Minimal runnable service with `README` and exact run commands.
- OpenAPI/Swagger contract for each API surface.
- Database schema and migration files.
- Tests demonstrating main flows and CI configuration snippet.
- Authorization-negative tests and cross-user isolation tests.
- Retry/idempotency behavior for financial and offline-sync writes.
- Country and language behavior when the endpoint is user-facing.

Prompt patterns:
- Task: "Implement endpoint `POST /api/transactions/sync` with a bounded batch, token-derived ownership, idempotency keys, per-operation results, tests, and an Alembic migration if needed."

Contributor notes:
- Keep endpoints small and documented in `backend-api/README.md` or `docs/TECHNICAL-GUIDE.md`.
- Never trust `user_id`, `organizer_id`, or similar identity fields from request bodies.
- Use `Decimal` for amounts and validate currency, identifiers, lengths, and batch sizes.
- Make retried writes idempotent and return explicit `accepted`, `already_processed`, or `rejected` states.
- Use `selectinload`/`joinedload`, composite indexes, pagination, and streaming for large reads/exports.
- Keep provider-specific payment logic behind an adapter and country-specific rules in `app/core/countries.py`.
- Payment integrations must model intents, external IDs, state transitions, reconciliation, refunds, disputes, provider idempotency, timeouts, and retries; never mark success from an unverified client response.
- Identity flows must use progressive tiers, validate country/phone consistency, store verification outcomes rather than raw biometric material, and require a trusted provider before advancing beyond Tier 0.
- Treat GraphQL as an additional API surface, not an authorization bypass; apply the same identity, ownership, pagination, and rate-limit rules as REST.
- Apply migrations explicitly; do not use `Base.metadata.create_all()` in production startup.
- Run `pytest -q`, migration upgrade tests, `python -m py_compile`, and `git diff --check` before review.

## Security checklist

- [ ] Authentication rejects missing or invalid identity subjects.
- [ ] Every resource read and mutation checks ownership or role permission.
- [ ] Webhooks verify raw-body signatures, timestamps, idempotency, and reconciliation state.
- [ ] Secrets fail closed and are never logged.
- [ ] Exports are authenticated, authorized, bounded, and streamed.
