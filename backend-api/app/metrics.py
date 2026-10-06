from prometheus_client import Counter, Histogram, Gauge
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request
import time

# Request metrics
HTTP_REQUEST_COUNT = Counter(
    'http_requests_total', 'Total HTTP requests', ['method', 'path', 'status']
)

HTTP_REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds', 'HTTP request duration', ['method', 'path']
)

# DB metrics
DB_CONNECTIONS = Gauge('db_active_connections', 'Active DB connections')

# SQL query latency histogram
DB_QUERY_LATENCY = Histogram('db_query_duration_seconds', 'DB query duration', ['query'])

# Celery metrics
CELERY_TASKS_TOTAL = Counter('celery_tasks_total', 'Total Celery tasks', ['task', 'status'])

def record_request(method, path, status, duration):
    HTTP_REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()
    HTTP_REQUEST_LATENCY.labels(method=method, path=path).observe(duration)


def record_db_query(query, duration):
    try:
        DB_QUERY_LATENCY.labels(query=query[:100]).observe(duration)
    except Exception:
        pass

def metrics_endpoint():
    data = generate_latest()
    return CONTENT_TYPE_LATEST, data

# Sign-in. A spike in otp_request/sent with no matching otp_verify/ok is SMS
# pumping: someone spending our SMS budget on numbers they never verify.
AUTH_EVENTS = Counter('hossouko_auth_events_total', 'Sign-in events', ['event', 'result'])

# Errors reported by the apps themselves (POST /api/client-events). Labels are
# bounded: app and kind are enums, versions are validated before use.
CLIENT_EVENTS = Counter(
    'hossouko_client_events_total', 'Errors reported by Hossouko apps', ['app', 'platform', 'kind', 'app_version']
)

# App usage (POST /api/usage-events). `name` is an allow-listed enum, so the
# label stays bounded; screens and content ids live in the table, not here.
USAGE_EVENTS = Counter('hossouko_usage_events_total', 'Usage events reported by Hossouko apps', ['app', 'name'])

# First launches, i.e. installs (a reinstall counts again: the install id is
# kept in the app's own storage).
APP_INSTALLS = Counter('hossouko_app_installs_total', 'First launches of Hossouko apps', ['app'])
