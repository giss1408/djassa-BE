# Djassa Application Security

## Security status

This document defines required controls. It is not a certification that every control is implemented. Current code is a prototype and must not process real financial traffic without identity, authorization, reconciliation, and regulatory review.

## Control matrix

| Control | Current status | Required before production |
|---|---|---|
| Non-root application container | Implemented | Verify in admission policy |
| Required JWT secret | Implemented | Add real identity provider and rotation |
| Token-derived resource ownership | Partial | Complete for every endpoint |
| Role-based access control | Partial | Define roles, permissions, and enforcement |
| Short-lived/revocable sessions | Not complete | Add refresh/revocation strategy |
| Webhook signature verification | Implemented in prototype | Test against each provider |
| Mandatory replay protection | Implemented in prototype | Verify provider timestamp semantics |
| Payment reconciliation | Not implemented | Required before financial use |
| Secrets manager integration | Manifest examples | Validate Vault identity and access policy |
| Image scanning | CI/Jenkins stage | Make failures blocking and sign images |
| Backups and restore tests | Documented requirement | Automate and verify recovery objectives |
| Centralized audit logs | Partial | Define retention, access, and alerting |

## Identity and authorization

- Never accept the authenticated user identity from a request body.
- Every read, export, mutation, and financial operation must check resource ownership or an explicit role permission.
- Define separate roles for customers, merchants, operators, administrators, and financial partners.
- Require MFA for administrators and infrastructure operators.
- Log sensitive actions with actor, resource, decision, timestamp, and correlation ID.
- Return generic authentication errors; keep diagnostic details in protected logs.

The current demo login must be replaced by a real user store or identity provider before production.

## Progressive identity and KYC

Identity assurance must match feature risk:

- **Tier 0:** phone or operator-linked identifier for loyalty only.
- **Tier 1:** phone verification plus approved liveness/selfie verification for tontine or partner savings workflows.
- **Tier 2:** national-ID capture and partner-approved cross-check before credit-history export.

These tiers are a product and control design, not a claim that an operator will expose KYC data. Confirm data-sharing authority, consent, retention, biometric processing, cross-border transfer, and deletion obligations with the licensed partner and qualified local counsel. Prefer a verification result or attestation over storing raw identity documents or biometric material. Never make basic loyalty conditional on high-friction verification.

## Federated identity boundary

The strategic identity direction is a federated trust and consent layer, not a central national identity database. Djassa should store scoped attestations and metadata such as issuer, assurance level, purpose, issue time, expiry, revocation status, and audit reference. It should not copy raw operator KYC records, biometric databases, or national-ID repositories unless a specific legal and operational mandate permits it.

Every federated integration must define:

- The authoritative issuer.
- The exact claim being exchanged.
- User consent and permitted purpose.
- Expiry and revocation behavior.
- Liability for incorrect or stale claims.
- Audit access and retention.
- Security, breach notification, and deletion responsibilities.

This identity-manager direction requires formal governance and regulatory approval before being presented as a production service in Côte d'Ivoire.

## Secrets

Required application variables:

- `DJASSA_SECRET_KEY`: JWT signing key; fail startup when missing.
- `MOBILE_MONEY_SECRETS`: comma-separated active and previous webhook keys.
- `DATABASE_URL`: PostgreSQL connection URL.
- `CELERY_BROKER_URL`: private Redis broker URL.

Secrets must come from Jenkins credentials, Docker secrets, Vault, or a cloud secret manager. Do not commit `.env`, credentials, tokens, or provider payloads.

## Webhook and payment controls

Every provider callback must:

1. Verify the signature over the exact raw request body.
2. Require and validate a timestamp within the configured replay window.
3. Validate payload shape, external ID, amount, currency, and expected transaction state.
4. Enforce database-backed idempotency under concurrency.
5. Record the event before acknowledging it.
6. Process business effects asynchronously with retries and a dead-letter path.
7. Reconcile provider settlement reports with the internal ledger.

A valid signature alone is never sufficient to credit money.

Payment state transitions are explicit: a payment starts as `created`, becomes `pending` after provider initiation, and can reach `succeeded`, `failed`, `cancelled`, or `disputed` only through an allowed transition. Refunds use `refund_pending` and `refunded`. Invalid transitions are rejected by the domain state machine.

## Data protection

- Collect only data needed for the declared user purpose.
- Make consent specific, visible, revocable, and auditable.
- Give users access to their own history and correction mechanisms.
- Encrypt data at rest and in transit according to the deployment environment.
- Mask phone numbers and payment references in logs.
- Do not copy production data into test environments without anonymization.
- Use expiring, authorized links for large exports.

## Network and runtime controls

- Expose only the ingress or reverse proxy publicly.
- Keep PostgreSQL, Redis, metrics, exporters, and worker endpoints private.
- Run containers as non-root with dropped capabilities, no privilege escalation, read-only filesystems where compatible, and `seccompProfile: RuntimeDefault` in Kubernetes.
- Apply default-deny NetworkPolicies and allow only required flows.
- Pin image versions or digests; scan and sign images before deployment.
- Set CPU and memory requests/limits.

## Production gate

Do not approve production deployment until all of these are true:

- [ ] Real identity provider and user lifecycle are implemented.
- [ ] Cross-user and cross-tenant authorization tests pass.
- [ ] Admin MFA and role permissions are enforced.
- [ ] Provider webhook, reconciliation, retry, and dispute workflows are tested.
- [ ] No placeholder or default secret exists.
- [ ] Image scan passes and the image is signed.
- [ ] Database backups have been restored successfully in a test environment.
- [ ] Metrics and logs are authenticated and contain no unnecessary personal data.
- [ ] Regulatory and partner responsibilities are approved in writing.
