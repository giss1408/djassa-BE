import os
from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery("fidelia",
                  broker=BROKER_URL,
                  backend=BACKEND_URL,
                  include=["app.celery_tasks"])

# Optional config
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # With Redis, a job whose worker died before acknowledging it (a video
    # conversion cut by a deploy or a crash) goes back to the queue after this
    # many seconds. Longer than the longest conversion (ffmpeg's own 15 min
    # cap, plus transfers), shorter than the 30 min after which the API calls
    # the video interrupted (app/api/media.py STALE_AFTER).
    broker_transport_options={'visibility_timeout': int(os.getenv('CELERY_VISIBILITY_TIMEOUT', '1200'))},
)

# Instrument Celery task events
from prometheus_client import Counter
CELERY_TASKS = Counter('celery_tasks_executed_total', 'Celery tasks executed', ['task_name', 'state'])

def record_task(task_name, state='success'):
    try:
        CELERY_TASKS.labels(task_name, state).inc()
    except Exception:
        pass
