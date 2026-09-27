# Contributing to Djassa

## Branches

- `main`: reviewed, releasable history.
- `integration`: development integration branch.
- Feature branches should be short-lived and named after the change.

## Before opening a pull request

From `backend-api`:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
python3 -m py_compile app/main.py
```

For schema changes, review [MIGRATIONS.md](backend-api/MIGRATIONS.md) and include the Alembic migration.

## Security requirements

- Never commit secrets, tokens, production data, or `.env` files.
- Derive ownership from the authenticated identity, not request-body identifiers.
- Add negative authorization tests for every financial or export endpoint.
- Verify webhook signatures, timestamps, idempotency, and reconciliation behavior.
- Do not add a financial feature without a documented regulatory and partner boundary.

## Pull request checklist

- [ ] The change has a focused description and tests.
- [ ] Existing API behavior is preserved or documented as a breaking change.
- [ ] Monetary values use `Decimal` and bounded validation.
- [ ] Database changes include a reviewed migration.
- [ ] Logs do not expose secrets or unnecessary personal data.
- [ ] Documentation and configuration examples are updated.
- [ ] `pytest -q` passes.

See [skills/README.md](skills/README.md) and [docs/TECHNICAL-GUIDE.md](docs/TECHNICAL-GUIDE.md) for implementation guidance.