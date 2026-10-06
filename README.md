# Hossouko

Hossouko turns everyday sales at neighbourhood shops into proof: a verified business history that the merchant owns and, with consent, can take to a licensed lender. It starts in Abidjan with merchant sales recording, loyalty and QR payments, then connects merchants and customers to licensed partners for digital tontines, savings and credit. Hossouko never holds funds or lends.

This repository is the platform behind the merchant app (`hossouko-App-retailer`), the customer app (`hossouko-App-user`) and the public site (`hossouko-Web`).

## Start here

- [Concept](docs/business/CONCEPT.md): what Hossouko is, for whom, and how to explain it to each audience.
- [Market](docs/business/MARKET.md): sourced figures, regulation and positioning.
- [Business model](docs/business/BUSINESS-MODEL.md): how the project creates and earns value.
- [Partners](docs/business/PARTNERS.md): who to contact and what to ask.
- [Roadmap](docs/business/ROADMAP.md): where we stand, phases and validation gates.
- [Technical guide](docs/technical/TECHNICAL-GUIDE.md): local development, deployment, and technical boundaries.
- [Contributing](CONTRIBUTING.md): branches, tests, security, and pull requests.
- [Documentation index](docs/README.md): complete product and technical documentation map.

## Repository structure

| Directory | Purpose |
|---|---|
| `backend-api/` | FastAPI API, PostgreSQL models, Celery worker, migrations, and tests |
| `Architecture/` | Target architecture, security, Kubernetes, and secret-management guidance |
| `docs/` | English product and technical decision documents plus source research |
| `monitoring/` | Prometheus, Grafana, Alertmanager, and exporter configuration |
| `skills/` | Contributor guidance, implementation patterns, and templates |

## Backend quick start

```bash
cd backend-api
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
docker compose -f docker-compose.dev.yml up -d db redis
export DATABASE_URL=postgresql+asyncpg://hossouko:hossouko@127.0.0.1:5432/hossouko
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run tests with `pytest -q`. Run the Celery worker separately as described in [TECHNICAL-GUIDE.md](docs/technical/TECHNICAL-GUIDE.md).

## VPS test deployment

For a disposable Ubuntu test server, use:

```bash
cd backend-api
./deploy-vps-test.sh
```

See [VPS-TEST-SERVER.md](docs/technical/VPS-TEST-SERVER.md) for firewall, SSH, secrets, migration, and access guidance.

## Jenkins CI/CD

The root [Jenkinsfile](Jenkinsfile) validates the source, builds the backend image, runs tests and migrations, creates an SBOM, scans the image with Trivy, and optionally publishes or deploys it.

Configure these Jenkins credentials before enabling deployment:

- `hossouko-container-registry-url`: secret text containing the registry hostname.
- `hossouko-container-registry`: username/password for the registry.
- `hossouko-vps-ssh`: SSH private key for the test VPS.
- `hossouko-vps-host`: secret text containing the VPS hostname.
- `hossouko-vps-user`: secret text containing the VPS deployment username.
- `hossouko-kubeconfig`: secret file for the Kubernetes deployment context.

The Jenkins agent must provide Docker, Python 3, `syft`, `trivy`, and `kubectl` when Kubernetes deployment is enabled. Kubernetes deployment requires `PUBLISH_IMAGE=true` and a `main` or `master` build. VPS test deployment is limited to the `integration` branch.

## Security status

This repository is a prototype and is not ready for production financial traffic. Authentication, authorization, payment reconciliation, secret management, backups, and regulatory controls require further work. Read [SECURITY.md](Architecture/SECURITY.md) before exposing any service.

## Contributor guidance

See [skills/README.md](skills/README.md) for research, writing, translation, technical reproducibility, and implementation guidance.