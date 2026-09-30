# VPS Test Server Setup

This guide sets up a temporary test server for the Djassa backend on an Ubuntu VPS. It is intended for integration testing and demos, not production financial traffic.

## 1. VPS requirements

Recommended minimum:

- Ubuntu 22.04 or 24.04 LTS
- 2 vCPU
- 4 GB RAM
- 40 GB SSD
- A static public IPv4 address
- A DNS record such as `test-api.example.com`

Keep PostgreSQL and Redis private. Only SSH and the HTTP/HTTPS reverse proxy should be reachable from the Internet.

## 2. Initial server hardening

Connect using the provider's temporary root access:

```bash
ssh root@VPS_IP
```

Update the operating system and create a deployment user:

```bash
apt update && apt -y upgrade
apt install -y ca-certificates curl git ufw unattended-upgrades
adduser deploy
usermod -aG sudo deploy
```

Install your SSH public key for the deployment user from your local machine:

```bash
ssh-copy-id deploy@VPS_IP
```

After confirming that key-based login works in a second terminal, disable root login and password authentication:

```bash
sudo install -d -m 0755 /etc/ssh/sshd_config.d
sudo tee /etc/ssh/sshd_config.d/99-djassa-test.conf >/dev/null <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sudo systemctl reload ssh
```

Enable the firewall. Keep port 8000 private; it is used only for local testing through an SSH tunnel or by a reverse proxy.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

## 3. Install Docker

Install Docker Engine and the Compose plugin:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
exit
```

Reconnect as `deploy`, then verify:

```bash
ssh deploy@VPS_IP
docker version
docker compose version
```

Do not expose the Docker daemon TCP socket. Do not add untrusted users to the `docker` group.

## 4. Get the application

Clone the repository into `/opt`:

```bash
sudo mkdir -p /opt/djassa
sudo chown deploy:deploy /opt/djassa
cd /opt/djassa
git clone YOUR_GIT_URL djassa
cd /opt/djassa/djassa/backend-api
```

For a test server, check out a known commit or tag rather than tracking a moving branch:

```bash
git checkout YOUR_TEST_COMMIT_OR_TAG
```

## 5. Preflight the application

Run these checks before starting containers:

```bash
python3 -m compileall app

docker compose -f docker-compose.poc.yml config
```

The current codebase must first pass the following application checks:

- `app.main` must create the FastAPI application before registering startup handlers.
- `app.api.webhooks` must import the shared `limiter` instance.
- The secret names must match the code: `DJASSA_SECRET_KEY` and `MOBILE_MONEY_SECRETS`.
- The hardcoded demo account and default JWT secret must not be used on an Internet-accessible server.

Until these are corrected, the container may fail during import or run with unsafe authentication defaults.

## 6. Configure test secrets

Generate strong, unique test-only values. Never reuse production secrets:

```bash
export DJASSA_SECRET_KEY="$(openssl rand -hex 32)"
export MOBILE_MONEY_SECRETS="$(openssl rand -hex 32)"
```

The current `docker-compose.poc.yml` requires database and application secrets through the private `.env` file. For a temporary test server, the automated deployment script creates these values and passes them to the services.

For repeatable testing, update the Compose file to use a private `.env` or Docker secrets and replace the hardcoded PostgreSQL password before deploying it anywhere beyond a disposable test VPS.

## 7. Start the test dependencies

Start PostgreSQL and Redis first:

```bash
docker compose -f docker-compose.poc.yml up -d db redis
```

Check their status and logs:

```bash
docker compose -f docker-compose.poc.yml ps
docker compose -f docker-compose.poc.yml logs --tail=100 db redis
```

Start the web service with the test secrets:

```bash
docker compose -f docker-compose.poc.yml run -d \
  --name djassa-web-test \
  --service-ports \
  -e DJASSA_SECRET_KEY="$DJASSA_SECRET_KEY" \
  -e MOBILE_MONEY_SECRETS="$MOBILE_MONEY_SECRETS" \
  web
```

Start the worker after the web service is healthy:

```bash
docker compose -f docker-compose.poc.yml up -d worker
```

The Compose file includes an optional Nginx service that expects `nginx/conf.d` to exist. Do not start that service until its configuration and TLS certificates are installed.

## 8. Database migrations

Run migrations from a Python virtual environment on the VPS, or from a one-off container that includes Alembic:

```bash
cd /opt/djassa/djassa/backend-api
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://djassa:djassa@127.0.0.1:5432/djassa
alembic -c alembic.ini upgrade head
```

The database port is not published by the Compose file, so the host command above will not reach the container unless PostgreSQL is separately published. Prefer running migrations from a container on the Compose network, or temporarily publish the port only on `127.0.0.1` and remove it afterward.

Example temporary migration container:

```bash
docker run --rm \
  --network backend-api_default \
  -e DATABASE_URL=postgresql+asyncpg://djassa:djassa@db:5432/djassa \
  -v "$PWD":/app -w /app python:3.11-slim \
  sh -c 'pip install -r requirements.txt && alembic -c alembic.ini upgrade head'
```

The Compose network name may differ. Check it with:

```bash
docker network ls
```

## 9. Automated deployment

After Docker is installed and the repository is checked out, run the automated test deployment from `backend-api`:

```bash
cd /opt/djassa/djassa/backend-api
./deploy-vps-test.sh
```

The script creates `.env` with random test secrets when needed, validates the Compose configuration, builds the API image, starts PostgreSQL and Redis, applies Alembic migrations, starts the API and worker, and verifies `/health`.

The previous `deploy-poc.sh` command remains as a compatibility wrapper:

```bash
./deploy-poc.sh
```

Do not commit the generated `.env` file. Review the service logs if deployment fails:

```bash
docker compose --project-name djassa-test --env-file .env -f docker-compose.poc.yml logs --tail=100 web worker
```

## 10. Verify the service

Check the container and application logs:

```bash
docker ps
docker logs --tail=200 djassa-web-test
```

The application port is published on the VPS by the `web` service. Test locally on the VPS:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

Do not open port 8000 in UFW. To access the API from your workstation without exposing it publicly, use an SSH tunnel:

```bash
ssh -N -L 8000:127.0.0.1:8000 deploy@VPS_IP
```

Then open `http://127.0.0.1:8000/docs` locally.

## 11. Test authentication and API behavior

The repository currently contains a demo authentication implementation. Use it only after confirming it has been removed or explicitly isolated from the test environment. Test the following before considering the server usable:

- Missing or invalid bearer tokens return `401`.
- User A cannot read or modify User B's transactions, consents, tontines, contributions, or exports.
- Tontine exports require authentication and group membership.
- Invalid and replayed webhook signatures are rejected.
- Webhook timestamps are mandatory and within the configured replay window.
- `/metrics` is not reachable through the public interface.

## 12. Logs and lifecycle

Inspect service logs:

```bash
docker compose -f docker-compose.poc.yml logs -f web worker
```

Restart the test stack:

```bash
docker compose -f docker-compose.poc.yml restart web worker
```

Stop it without deleting database data:

```bash
docker compose -f docker-compose.poc.yml down
```

Remove the disposable database volume only when the test data is no longer needed:

```bash
docker compose -f docker-compose.poc.yml down -v
```

## 13. Test-server safety checklist

Before sharing the server address:

- [ ] SSH keys work and password login is disabled.
- [ ] UFW allows only SSH, HTTP, and HTTPS.
- [ ] PostgreSQL, Redis, and port 8000 are not publicly exposed.
- [ ] Test secrets are random and are not committed to Git.
- [ ] No production data or production credentials are present.
- [ ] The application does not use `change-me-in-prod`, `please-change-me`, or `demo/demo123`.
- [ ] The image is pinned to a commit or immutable digest.
- [ ] The API has been tested for cross-user access and webhook replay.
- [ ] The VPS has a destruction date and disposable test data.

This setup is suitable for controlled testing only. Production requires managed secrets, TLS termination, backups, patching, monitoring, access control, immutable images, and a completed authorization review.
