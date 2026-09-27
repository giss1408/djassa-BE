# Container and Kubernetes Security

This is the operational hardening guide for Docker Compose, Kubernetes, image supply chain, and runtime controls. The [application security guide](SECURITY.md) covers identity, data, and payment behavior.

## Environment model

| Environment | Canonical entry point | Purpose | Security posture |
|---|---|---|---|
| Local development | `backend-api/docker-compose.dev.yml` | Developer feedback loop | Disposable data; never shared or internet-facing |
| VPS integration test | `backend-api/deploy-vps-test.sh` | Controlled integration testing | Private dependencies, localhost API binding, test secrets |
| Kubernetes target | `Architecture/k8s/` and `scripts/deploy-k8s.sh` | Staging/production-shaped deployment | Requires cluster policy, secret store, TLS, and reviewed values |

Do not use the local or VPS test configuration for production financial traffic.

## Image supply chain

1. Build images only in controlled CI/CD workers.
2. Pin base images and dependency versions where practical.
3. Generate an SBOM with Syft for every release image.
4. Fail the pipeline on unresolved Critical/High vulnerabilities according to the approved policy.
5. Sign release images with Cosign.
6. Enforce signature verification and disallow mutable tags through admission policy.
7. Retain the image digest, SBOM, scan report, source commit, and deployment record together.

The root `Jenkinsfile` implements build, test, migration, SBOM, scan, publish, and gated deployment stages. Image signing and admission enforcement remain cluster responsibilities.

## Kubernetes runtime baseline

Every production workload should define:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

Also require resource requests and limits, liveness/readiness probes, an immutable image reference, and a dedicated ServiceAccount.

## Network policy baseline

Start with deny-all ingress and egress in the application namespace. Add only required flows:

- Ingress controller to API on TCP 8000.
- API to PostgreSQL on TCP 5432.
- API/worker to Redis on TCP 6379.
- API/worker to object storage only when the feature is enabled.
- DNS egress to the cluster DNS service.
- HTTPS egress only for explicitly approved external providers.

The current example NetworkPolicy must be checked against real namespace labels, database labels, and DNS requirements before enforcement.

## Secrets baseline

Use External Secrets or a cloud secret manager. The application contract is:

```text
DATABASE_URL
DJASSA_SECRET_KEY
MOBILE_MONEY_SECRETS
CELERY_BROKER_URL
```

Do not place values in manifests, images, Git, or Jenkins logs. Rotate keys using an overlap window, deploy consumers that accept the new key, remove the old key, and verify provider callbacks afterward.

## Runtime operations

- Centralize application, ingress, audit, and Kubernetes logs.
- Do not expose Prometheus, Grafana, Alertmanager, Redis, PostgreSQL, or exporter ports publicly.
- Alert on readiness failures, 5xx rate, webhook rejection spikes, queue age, database storage, and backup failures.
- Use Falco or an equivalent runtime detector for privilege escalation and unexpected network behavior.
- Enable Kubernetes audit logs and retain them in tamper-resistant storage.
- Test database restore and incident-response procedures regularly.

## Kubernetes deployment checklist

- [ ] Namespace exists and has restricted Pod Security admission.
- [ ] External Secrets Operator and provider authentication are installed.
- [ ] Registry pull secret exists and has least privilege.
- [ ] Image is published by CI and referenced by digest or immutable tag.
- [ ] ServiceAccount, Role, and RoleBinding names match the Deployment.
- [ ] Ingress hostname and certificate issuer are real values.
- [ ] NetworkPolicy allows DNS and all required application flows.
- [ ] Resource limits and probes are configured.
- [ ] Rollout and rollback commands have been tested.
