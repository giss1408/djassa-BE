# External Secrets Contract

This document defines how Kubernetes obtains application secrets. It is a deployment contract, not a place to store secret values.

## Application secret names

The generated Kubernetes Secret must expose these keys exactly:

| Kubernetes key | Application use |
|---|---|
| `DATABASE_URL` | PostgreSQL connection URL |
| `DJASSA_SECRET_KEY` | JWT signing key |
| `MOBILE_MONEY_SECRETS` | Active and previous webhook signing keys, newest first |
| `CELERY_BROKER_URL` | Redis broker URL |

Do not use the old names `JWT_SECRET` or `MOBILE_MONEY_SECRET`; the application does not read them.

## Required deployment sequence

1. Install External Secrets Operator.
2. Configure a namespaced `SecretStore` or approved `ClusterSecretStore`.
3. Grant the operator least-privilege access to the selected Vault path.
4. Create an `ExternalSecret` in the same namespace as the API Deployment.
5. Wait for the generated Secret to reach `Ready`.
6. Deploy or restart the API and worker.
7. Verify `/ready`, logs, and webhook signature behavior.

## Example ExternalSecret

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: djassa-app-secrets
  namespace: djassa
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: djassa-vault
    kind: SecretStore
  target:
    name: djassa-app-secrets
    creationPolicy: Owner
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: djassa/production
        property: database_url
    - secretKey: DJASSA_SECRET_KEY
      remoteRef:
        key: djassa/production
        property: jwt_secret
    - secretKey: MOBILE_MONEY_SECRETS
      remoteRef:
        key: djassa/production
        property: mobile_money_secrets
    - secretKey: CELERY_BROKER_URL
      remoteRef:
        key: djassa/production
        property: celery_broker_url
```

## Rotation procedure

1. Generate a new key in the secret manager.
2. For webhook signing, store the new key first and retain the previous key during the provider overlap window.
3. Roll the API and worker so all replicas load the same key list.
4. Update the external provider configuration.
5. Confirm valid callbacks and rejected old callbacks according to the agreed window.
6. Remove the old key and roll again.
7. Record the rotation, operator, affected services, and verification result.

JWT rotation requires a session strategy: rotating the signing key invalidates existing tokens unless a planned key-ring or forced reauthentication process is used.

## Example SecretStore shape

The Vault authentication method, namespace, path, and token source are environment-specific. Never commit a production Vault token. The example manifests under `k8s/` must be edited for the target cluster and namespace before use.
