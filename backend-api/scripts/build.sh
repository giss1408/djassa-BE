#!/usr/bin/env bash
set -euo pipefail

# Build Docker image for backend-api
cd "$(dirname "$0")/.."

: ${TAG:=registry.example.com/fidelia/api:dev}

echo "Building Docker image ${TAG}"
docker build -t ${TAG} .
echo "Built ${TAG}"
