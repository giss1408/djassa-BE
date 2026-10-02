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
| App errors (`AppErrorSpike`) | More than 50 reports per app version in 30 minutes | Read the stacks with `GET /api/admin/client-events?app=<app>&days=1` |
| App crashes (`AppCrashAfterRelease`) | More than 10 crashes per app version in 1 hour | Halt the store rollout of that version, then fix |
| Sign-in codes unverified (`OtpSentButNotVerified`) | Under 30% of codes verified, over 30 sent in an hour | SMS pumping or silent delivery failure: check the provider dashboard, tighten limits |
| SMS delivery (`OtpDeliveryFailing`) | More than 5 refused sends in 15 minutes | Provider credit, sender ID or outage; nobody can sign in meanwhile |

## Rules for new alerts

- Include the service, environment, severity, and runbook link.
- Alert on user impact or financial risk, not only infrastructure noise.
- Do not include personal data, tokens, or webhook payloads in alert text.
- Test the alert and escalation path before relying on it.

## Access control

Prometheus, Grafana, Alertmanager, and exporter endpoints are internal monitoring services. Do not expose them publicly with default credentials. Change the local Grafana password before any shared environment and place dashboards behind authenticated access.