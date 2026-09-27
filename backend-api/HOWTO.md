# Djassa Backend — HOWTO

This document explains local development and CI for the backend. For the project overview, start with [the root README](../README.md). For the complete technical map, see [the technical guide](../docs/TECHNICAL-GUIDE.md).

Do not commit credentials. Use environment variables, a private `.env`, or a managed secret store.

## 1) Prepare a Python virtual environment

```bash
cd backend-api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Running with local Postgres (recommended)

Start Postgres using the provided `docker-compose.dev.yml`:

```bash
docker compose -f docker-compose.dev.yml up -d db
```

Set the `DATABASE_URL` env var for the app and Alembic:

```bash
export DATABASE_URL=postgresql+asyncpg://djassa:djassa@127.0.0.1:5432/djassa
```

Apply database migrations (Alembic):

```bash
alembic -c alembic.ini upgrade head
```

See [MIGRATIONS.md](MIGRATIONS.md) before creating or rolling back schema changes.

Run the development server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs for the OpenAPI docs.

## 3) Running without Postgres (SQLite fallback)

By default the app falls back to `sqlite+aiosqlite:///./test.db` if `DATABASE_URL` is not set. This is convenient for quick local experiments but not recommended for CI or production.

To run with the fallback DB:

```bash
unset DATABASE_URL
uvicorn app.main:app --reload
```

## 4) Running tests

Use the virtualenv and ensure dependencies are installed. For the fastest parity with CI, start the local Postgres service first and set `DATABASE_URL` as above, then run:

```bash
pytest -q
```

If you prefer to run tests against SQLite (quick run), unset `DATABASE_URL` and run `pytest -q` — note that some integration behaviours may differ.

## 5) Running the app in Docker (build and run)

Build the image:

```bash
docker build -t registry.example.com/djassa/api:dev .
```

Run with environment variables (example):

```bash
docker run -e DATABASE_URL=postgresql+asyncpg://djassa:djassa@db:5432/djassa -p 8000:8000 registry.example.com/djassa/api:dev
```

## 6) CI notes

- GitHub Actions workflow runs the SBOM and Trivy scans, starts a Postgres service, waits for it to be ready, runs Alembic migrations, and then runs `pytest`.
- Store registry credentials and any production database credentials as GitHub Secrets (e.g. `REGISTRY_URL`, `REGISTRY_USERNAME`, `REGISTRY_PASSWORD`).

### Add Trivy image scan to GitHub Actions

Add a workflow step that runs Trivy against the built image and fails if critical vulnerabilities are found. Example job snippet:

```yaml
- name: Scan image with Trivy
	uses: aquasecurity/trivy-action@v0.3.0
	with:
		image-ref: registry.example.com/djassa/api:dev
		exit-code: '1'
		severity: CRITICAL
		format: 'table'
```

## 7) Background worker (Celery + Redis)

Start Redis and the worker in a second terminal:

```bash
docker compose -f docker-compose.dev.yml up -d redis
export CELERY_BROKER_URL=redis://127.0.0.1:6379/0
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
celery -A app.celery_app.celery_app worker --loglevel=info
```

See [README-CELERY.md](README-CELERY.md) for worker and scheduled-task details.

## 8) Security & secrets

- Do not commit `.env` files or credentials. Use environment variables or a secrets manager (External Secrets in Kubernetes is configured in `Architecture/k8s/external-secret-example.yaml`).
- The file `.gitignore` already excludes `.env`, `.venv`, `infra/secrets/` and common credential file extensions.
- The application expects `DJASSA_SECRET_KEY` for JWT signing and `MOBILE_MONEY_SECRETS` for webhook verification.
- Never use demo credentials or placeholder secrets on an Internet-accessible server.

## 9) Useful commands summary

```bash
# start postgres locally
docker compose -f docker-compose.dev.yml up -d db

# run migrations
export DATABASE_URL=postgresql+asyncpg://djassa:djassa@127.0.0.1:5432/djassa
alembic -c alembic.ini upgrade head

# run server
uvicorn app.main:app --reload

# run tests
pytest -q
```

If you want, I can add a `Makefile` or convenience `scripts/` wrappers for these commands. Which would you prefer? 

## 9) MVP / PoC Deployment Options (cheap, practical)

This section documents practical, low-cost ways to deploy a working PoC or MVP for `djassa`. Choose one depending on how much automation, uptime, and budget you need.

Summary of recommended providers:
- **Hetzner Cloud**: best price-to-performance for a single VPS. Pick a CX11/CX21 instance (1–2 vCPU, 2GB RAM) for €3.49–€6/month depending on region and specs.
- **Scaleway**: low-cost ARM/AMD instances and quick setup for small projects.
- **Vultr / DigitalOcean / Linode**: $5–6/month tiers, very easy to use and widely documented.
- **Managed container platforms (Render, Fly, Railway)**: slightly more expensive but remove infra management; good for fast demos.

Minimal architecture for a single-VPS PoC:
- Services: `web` (FastAPI + Uvicorn), `db` (Postgres), `redis` (Celery broker), `worker` (Celery), optionally `nginx` reverse proxy. Keep monitoring and Grafana optional to reduce resource use.
- Persistence: use the VPS disk or attach a small volume for Postgres data.
- Security: run behind `nginx` with TLS (Let's Encrypt), store secrets in environment variables or a secrets manager.

Trade-offs:
- Pros: extremely low cost, simple to iterate, easy to debug.
- Cons: single point of failure, limited scaling, less production-hardened monitoring and backups.

Minimal steps to deploy on a cheap Ubuntu VPS (generic)

1) Provision VM on chosen provider (1–2GB RAM recommended).
2) SSH to the machine and install Docker + Docker Compose (or Podman).

Example commands (Ubuntu):

```bash
# on your local machine: create SSH key and provision VPS via provider UI/CLI
ssh root@YOUR_VPS_IP

# on the VPS: install Docker
apt update && apt install -y ca-certificates curl gnupg lsb-release
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
useradd -m -s /bin/bash deploy || true
usermod -aG docker deploy
apt install -y docker-compose-plugin
mkdir -p /opt/djassa && chown deploy:deploy /opt/djassa
exit

# from local machine: copy repo or push image to registry and pull on VPS
scp -r ./backend-api deploy@YOUR_VPS_IP:/home/deploy/djassa-backend
ssh deploy@YOUR_VPS_IP
cd /home/deploy/djassa-backend
docker compose -f docker-compose.poc.yml up -d --build
```

Notes: If you prefer not to build on the VPS, build multi-arch images in CI and `docker pull` on the server instead.

Environment variables (example `.env`):

```ini
# Database
DATABASE_URL=postgresql+asyncpg://djassa:djassa@db:5432/djassa

# Redis
CELERY_BROKER_URL=redis://redis:6379/0

# Web
DJASSA_SECRET_KEY=replace-with-random
MOBILE_MONEY_SECRETS=...
```

Optional monitoring: omit Prometheus/Grafana for the smallest VPS. If you need traces, run the OTEL collector on a separate small instance or use a managed provider (Grafana Cloud).

Backups & persistence:
- Schedule `pg_dump` backups to another storage (object store or another server).
- Snapshot the VPS disk if the provider supports it.

When to move off a single VPS:
- You need higher availability, scaling, or stronger isolation. Next steps: use managed Postgres, add a small Kubernetes cluster (k3s/AKS/GKE/ACA), or deploy to a managed container service.

## 10) Included convenience files

I added a minimal PoC compose file (`docker-compose.poc.yml`) and a simple `deploy-poc.sh` helper script in this directory to bootstrap the stack on a fresh Ubuntu server. Edit env values before running.

## 11) Africa reachability & VPS configuration (recommended)

This subsection covers steps and tuned settings to maximize reachability and reliability for users in Africa while keeping costs low.

- Regions to prefer:
	- **South Africa** (AWS `af-south-1` — Cape Town, Azure South Africa North/West) gives best latency inside southern Africa.
	- If African regions are unavailable or expensive, use nearby European regions (Frankfurt, Amsterdam) + an edge/CDN.

- Networking & DNS:
	- Use Cloudflare (or similar) in front of the VPS for geo-routing, TLS termination, and IP stability.
	- If partners require a static IP for webhooks, use the provider's reserved/static IP or a small load balancer.

- VPS hardware (recommended tiers):
	- Minimal cheap (for experiments): 1 vCPU, 2 GB RAM, 20 GB SSD, 1–2 GB swap.
	- Recommended PoC (balanced): 1–2 vCPU, 2–4 GB RAM, 40 GB SSD, 2 GB swap.
	- Comfortable dev/staging: 2 vCPU, 4 GB RAM, 80 GB SSD, 4 GB swap.

- OS & system tuning (Ubuntu recommended):

1) Create swap (if RAM <= 4GB):

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

2) Firewall (allow SSH, HTTP/HTTPS, webhook port):

```bash
sudo apt update && sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

3) Docker configuration: add the user to `docker` group and enable overlay2 storage (default Docker install handles this). Keep image builds in CI and `docker pull` on the VPS when possible to reduce build-time memory pressure.

4) Kernel tuning (small):

```bash
sudo sysctl -w net.core.somaxconn=1024
sudo sysctl -w vm.swappiness=10
```

- Postgres (tiny tuning for 2GB VPS): add these to `postgresql.conf` or use a custom image/config:

```
shared_buffers = 256MB
effective_cache_size = 512MB
work_mem = 4MB
maintenance_work_mem = 64MB
max_connections = 50
```

- Redis (small instance): set in `redis.conf` or Docker environment:

```
maxmemory 256mb
maxmemory-policy allkeys-lru
```

- Celery & Uvicorn recommended options for small VPS:
	- Start Uvicorn with 1 worker: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`
	- Run Celery worker with concurrency 1: `celery -A app.celery_app worker --concurrency=1 --loglevel=info`

- Docker-Compose resource hints (example snippet to include in `docker-compose.poc.yml` service entries):

```yaml
services:
	web:
		deploy:
			resources:
				limits:
					memory: 750M
	worker:
		deploy:
			resources:
				limits:
					memory: 512M
	db:
		deploy:
			resources:
				limits:
					memory: 1024M
```

Note: `deploy.resources` is ignored by local Docker Compose v1; it's used by swarm/k8s. Use explicit container `mem_limit` fields or use systemd-run limits on small servers if needed.

- TLS and webhook endpoints:
	- Use Cloudflare or a TLS reverse proxy (`nginx` + `certbot`) and publish the HTTPS endpoint to mobile-money partners.
	- Test partner webhook delivery from their test systems and verify signature, idempotency, and replay protection (see `app/api/webhooks.py`).

- Backups & persistence:
	- Schedule `pg_dump` nightly to an object store (S3/Spaces) and rotate backups.
	- Snapshot the VPS disk before major changes.

- Monitoring (optional on PoC):
	- Avoid running Prometheus + Grafana on the same 2GB VPS; use external managed monitoring or run only exporters and a lightweight health-check script.

Checklist for provisioning a PoC in Africa-friendly region:
- Provision small VM in South Africa region (or nearest region) with 2–4 GB RAM.
- Install Docker and Docker Compose, create swap, enable UFW.
- Reserve a static IP if partner needs IP whitelisting.
- Put Cloudflare in front for TLS and DDoS protection; use a Page Rule or proxy only the webhook domain if necessary.
- Start stack with `docker compose -f docker-compose.poc.yml up -d --build` and verify `/health` and webhook endpoints.

If you want, I will append small config files (`postgres.conf.tiny`, `redis.conf.tiny`) and a short `provision-vps.sh` to automate these OS-level steps. Should I add those files now?
