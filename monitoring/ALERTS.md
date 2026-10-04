# Monitoring and Alerting

Monitoring configuration lives in this directory. Thresholds must be tuned with real pilot traffic; the following are initial operational targets.

## Alerts

The rules are in [`rules/alerts.yml`](rules/alerts.yml), loaded by the local
Prometheus and, in production, by Grafana Cloud. What to do when each fires:
[`docs/technical/PRODUCTION.md` § 7](../docs/technical/PRODUCTION.md#7-when-an-alert-fires).

| Alert | Fires when | Severity |
|---|---|---|
| `ApiMetricsMissing` | No metrics from the API for 5 minutes | critical |
| `HighErrorRate` | More than 5% of requests answer 5xx for 5 minutes | critical |
| `SlowRequests` | p95 latency above 2 s for 10 minutes (media uploads excluded) | warning |
| `PaymentWebhookFailing` | More than 3 refused payment webhooks in 15 minutes | critical |
| `AppErrorSpike` | More than 50 error reports per app version in 30 minutes | warning |
| `AppCrashAfterRelease` | More than 10 crashes per app version in 1 hour | critical |
| `OtpSentButNotVerified` | Under 30% of codes verified, over 30 sent in an hour | critical |
| `OtpDeliveryFailing` | More than 5 refused SMS sends in 15 minutes | critical |
| `OtpDailyBudgetReached` | `OTP_DAILY_SMS_BUDGET` spent: sign-in codes paused | critical |

Thresholds are starting points: tune them with real pilot traffic. Outside the
rules, an uptime monitor checks `/ready` every minute (PRODUCTION.md § 4).

Not covered yet, to add when they run in production: database storage and
connections (Neon's own alerts), Redis memory and Celery queue age (no worker
runs on Render today).

## Rules for new alerts

- Include the service, environment, severity, and runbook link.
- Alert on user impact or financial risk, not only infrastructure noise.
- Do not include personal data, tokens, or webhook payloads in alert text.
- Test the alert and escalation path before relying on it.

## Access control

Prometheus, Grafana, Alertmanager, and exporter endpoints are internal monitoring services. Do not expose them publicly with default credentials. Change the local Grafana password before any shared environment and place dashboards behind authenticated access.