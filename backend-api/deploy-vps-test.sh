#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.poc.yml"
ENV_FILE="${ROOT_DIR}/.env"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-hossouko-test}"

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup_on_error() {
  status=$?
  if [[ $status -ne 0 ]]; then
    printf '\n[deploy] Deployment failed. Recent service logs:\n' >&2
    docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=80 db redis web worker >&2 || true
  fi
  exit "$status"
}
trap cleanup_on_error EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

require_command docker
require_command openssl
require_command curl

docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"
[[ -f "$COMPOSE_FILE" ]] || fail "Compose file not found: $COMPOSE_FILE"

cd "$ROOT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  log "Creating a private test environment file"
  db_password="$(openssl rand -hex 24)"
  jwt_secret="$(openssl rand -hex 32)"
  webhook_secret="$(openssl rand -hex 32)"
  cat > "$ENV_FILE" <<EOF
POSTGRES_USER=hossouko
POSTGRES_PASSWORD=${db_password}
POSTGRES_DB=hossouko
DATABASE_URL=postgresql+asyncpg://hossouko:${db_password}@db:5432/hossouko
CELERY_BROKER_URL=redis://redis:6379/0
HOSSOUKO_SECRET_KEY=${jwt_secret}
MOBILE_MONEY_SECRETS=${webhook_secret}
EOF
  chmod 600 "$ENV_FILE"
else
  [[ "$(stat -c '%a' "$ENV_FILE")" == "600" ]] || fail "$ENV_FILE must have mode 600"
fi

set -a
. "$ENV_FILE"
set +a

for required in POSTGRES_PASSWORD DATABASE_URL HOSSOUKO_SECRET_KEY MOBILE_MONEY_SECRETS; do
  [[ -n "${!required:-}" ]] || fail "$required is missing from $ENV_FILE"
done

case "$HOSSOUKO_SECRET_KEY" in
  change-me*|please-change-me|replace-with-random) fail "HOSSOUKO_SECRET_KEY is a placeholder" ;;
esac
case "$MOBILE_MONEY_SECRETS" in
  change-me*|please-change-me|replace-with-random) fail "MOBILE_MONEY_SECRETS is a placeholder" ;;
esac

compose() {
  docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

log "Validating Compose configuration"
compose config --quiet

log "Building the application image"
compose build web worker

log "Starting PostgreSQL and Redis"
compose up -d db redis

log "Waiting for PostgreSQL"
for attempt in $(seq 1 30); do
  if compose exec -T db pg_isready -U "${POSTGRES_USER:-hossouko}" -d "${POSTGRES_DB:-hossouko}" >/dev/null 2>&1; then
    break
  fi
  [[ "$attempt" -eq 30 ]] && fail "PostgreSQL did not become ready"
  sleep 2
done

log "Applying database migrations"
compose run --rm --no-deps web alembic upgrade head

log "Starting API and worker"
compose up -d web worker

log "Waiting for the API"
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null; then
    break
  fi
  [[ "$attempt" -eq 30 ]] && fail "API health check failed"
  sleep 2
done

trap - EXIT
log "Deployment completed"
compose ps
log "API is available locally at http://127.0.0.1:8000"
log "Use an SSH tunnel for remote access: ssh -N -L 8000:127.0.0.1:8000 deploy@VPS_IP"
