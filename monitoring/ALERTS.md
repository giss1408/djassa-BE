# Monitoring and Alerting

Monitoring configuration lives in this directory. Thresholds must be tuned with real pilot traffic; the following are initial operational targets.

## Initial alerts

| Signal | Initial threshold | Response |
|---|---|---|
| API 5xx rate | More than 5% for 5 minutes | Check API logs and database health |
| Webhook rejection rate | More than 5% for 5 minutes | Check provider signature, clock, and secret rotation |
| API readiness failures | Two consecutive probe failures | Stop rollout and inspect dependencies |
| PostgreSQL storage | More than 80% full | Expand storage or archive data |
| PostgreSQL connections | More than 80% of limit | Check leaks and pool sizing |
| Redis memory | More than 80% of limit | Inspect queue backlog and retention |
| Celery queue age | Older than 5 minutes | Check worker health and downstream providers |

## Rules for new alerts

- Include the service, environment, severity, and runbook link.
- Alert on user impact or financial risk, not only infrastructure noise.
- Do not include personal data, tokens, or webhook payloads in alert text.
- Test the alert and escalation path before relying on it.

## Access control

Prometheus, Grafana, Alertmanager, and exporter endpoints are internal monitoring services. Do not expose them publicly with default credentials. Change the local Grafana password before any shared environment and place dashboards behind authenticated access.