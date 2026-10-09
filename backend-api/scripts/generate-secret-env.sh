#!/usr/bin/env bash
set -euo pipefail

# Helper to export secrets from Kubernetes ExternalSecret/Secret to local env file (dev convenience only)
# Requires kubectl configured and access to cluster

NAMESPACE=${1:-default}
SECRET_NAME=${2:-fidelia-secrets}

kubectl get secret -n "$NAMESPACE" "$SECRET_NAME" -o json | jq -r '.data | to_entries[] | "\(.key)=\(.value | @base64d)"' > .env.local
echo "Wrote .env.local (keep out of git)"
