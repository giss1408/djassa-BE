# Djassa Architecture

This directory contains the technical architecture and deployment contracts for Djassa.

## Status model

- **Implemented:** present in the backend or validated deployment path.
- **Partial:** some code or manifests exist, but production controls are incomplete.
- **Target:** intended design that still requires implementation or operational approval.

The repository is a prototype. The target architecture must not be treated as proof that every control is active.

## Documents

| Document | Scope |
|---|---|
| [Architecture](ARCHITECtURE.md) | System boundaries, services, data flows, and deployment modes |
| [Application security](SECURITY.md) | Identity, authorization, data, webhook, and financial controls |
| [Container and Kubernetes security](security-architecture.md) | Image supply chain, runtime hardening, network policies, and operations |
| [External secrets](EXTERNAL-SECRETS.md) | Secret names, Vault/External Secrets contract, and rotation |
| [Kubernetes manifests](k8s/) | Deployment examples for a Kubernetes environment |
| [Docker Compose target](docker-compose.yml) | Hardened target topology; not the same as the lightweight VPS test stack |

## Deployment modes

### Local development

Uses `backend-api/docker-compose.dev.yml` for PostgreSQL and Redis, with the API and worker run from the developer environment.

### VPS integration test

Uses `backend-api/deploy-vps-test.sh` and `backend-api/docker-compose.poc.yml`. The API is bound to localhost, test secrets are generated locally, and migrations run before the API starts.

### Kubernetes target

Uses the manifests in `k8s/` with an ingress, External Secrets, restricted pod settings, and NetworkPolicy. These manifests require cluster-specific values and must be reviewed before use.

## Non-negotiable boundaries

- PostgreSQL, Redis, metrics, and worker services are private.
- Financial operations require authenticated identity and resource authorization.
- Webhooks are untrusted input and require signature, timestamp, idempotency, and reconciliation controls.
- Djassa does not hold deposits or lend directly without the required regulated partner or authorization.
- Secrets are injected at deployment time and are never committed to Git or baked into images.

## Current production blockers

- The current authentication implementation is a demo skeleton, not a production identity system.
- Role-based access control and complete resource authorization are still being developed.
- Payment-provider reconciliation and financial state transitions require real provider integration.
- Backup/restore, incident response, image signing, and admission enforcement need operational setup.
- Kubernetes manifests contain example hostnames, registry values, and provider references that must be replaced.

See the [technical guide](../docs/TECHNICAL-GUIDE.md) for implementation and deployment navigation.
