Celery worker and Redis (dev)

1) Start Redis (we provide a redis service in `docker-compose.dev.yml`):

```bash
docker compose -f docker-compose.dev.yml up -d redis
```

2) Export broker URL and start worker:

```bash
export CELERY_BROKER_URL=redis://127.0.0.1:6379/0
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
celery -A app.celery_app.celery_app worker --loglevel=info
```

3) Periodic tasks: use `celery beat` or a Kubernetes CronJob for scheduled jobs.

## Scheduled tasks

Neither is registered in a beat schedule here on purpose: the schedule belongs to
the deployment (`celery beat` or a Kubernetes CronJob), so it is not duplicated in
application code.

| Task | Suggested cadence | Why it exists |
|---|---|---|
| `placements.expire_finished` | every 15 min | Drops a finished featured-slot campaign out of the carousel. Reads are defended anyway (`list_deals` filters on live placements), so a missed run only leaves `Deal.is_featured` briefly stale. |
| `sale_events.report_quarantine` | daily | Logs a warning while migration `0014_sale_events` still has declared sales it could not attach to a venue. Those are real amounts belonging to nobody we can name and are excluded from every revenue figure — the count has to stay visible until it is zero. Resolve via `GET /api/admin/sale-events/quarantined`. |

Run one by hand:

```bash
celery -A app.celery_app.celery_app call sale_events.report_quarantine
```
