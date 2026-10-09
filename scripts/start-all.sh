#!/usr/bin/env bash
set -euo pipefail

# Cross-arch build and start for backend and monitoring
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

ARCH=${1:-$(uname -m)}
echo "Selected arch: ${ARCH}"

cd ${ROOT_DIR}/backend-api
echo "Building backend image for ${ARCH} (uses Docker buildx if available)"
if docker buildx version >/dev/null 2>&1; then
  docker buildx build --platform linux/${ARCH} -t fidelia-api:local --load .
else
  docker build -t fidelia-api:local .
fi

echo "Starting dev compose (db + redis + api)"
cd ${ROOT_DIR}/backend-api
docker-compose -f docker-compose.dev.yml up -d --build

echo "Starting monitoring stack"
${ROOT_DIR}/scripts/start-monitoring.sh

echo "All services started."
