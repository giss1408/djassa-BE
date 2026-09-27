# Skill: Technical, Reproducibility & Operations

Purpose: ensure Djassa code, data, deployments, and operational decisions are reproducible and well-documented.

When to use:
- Preparing data tables, scripts, migrations, CI/CD pipelines, architecture changes, or reproducible analysis.

Requirements:
- State the environment, dependency versions, required secrets, and exact commands.
- Prefer Docker or the repository's declared virtual environment for repeatable execution.
- Include migration, rollback, health-check, and cleanup commands for operational changes.
- Do not include real credentials, personal data, or provider payloads in examples.
- Test Kubernetes YAML with a local parser and validate against a real cluster before deployment.
- Record whether a feature is Implemented, Partial, or Target architecture.

Prompt pattern:
- Task: "Implement <change>, document the environment and exact commands, add tests and migration steps, and state any external dependency or production blocker."

Contributor notes:
- Backend commands normally run from `backend-api`.
- Schema changes require an Alembic migration and a clean-database upgrade test.
- CI changes must be reflected in `Jenkinsfile` and documented credentials/tooling.
- Low-connectivity workflows require idempotency keys, retry behavior, payload limits, and explicit sync states.
- Country-specific behavior belongs in `app/core/countries.py` or a provider adapter, not scattered through routes.
