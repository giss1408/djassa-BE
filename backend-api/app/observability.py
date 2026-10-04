"""What production monitoring reads: request metrics, the /metrics gate, logs.

* **Metrics** are labelled with the route template ("/api/venues/{venue_id}"),
  never the raw path: one series per route, not one per id or per URL a
  scanner tries. A hosted Prometheus bills per series, and an unbounded label
  is also memory anyone can make the API spend.
* **/metrics** is open only where `DJASSA_ENV` is unset (development, tests).
  A deployed API answers it only with `METRICS_TOKEN`, as a bearer token or as
  the password of HTTP basic auth (what Grafana Cloud's scrape job sends), and
  answers 404 otherwise, so the endpoint does not advertise itself.
* **Logs**: one line per request on the `djassa.access` logger, with the route
  template, status, duration and a request id echoed in `X-Request-ID`. No
  query string, no IP, no body: query strings carry phone numbers
  (`/api/admin/users?phone=`). `LOG_FORMAT=json` writes JSON lines for a log
  service; run uvicorn with `--no-access-log` so its own access log, which
  does print query strings, stays off.
"""

import base64
import hmac
import json
import logging
import os
import sys
import time
import uuid

from fastapi import Request
from prometheus_client import Gauge

from .metrics import record_request

access_log = logging.getLogger("djassa.access")

# Which build is running: a deploy shows as the commit label changing, so a
# dashboard can line up an error spike with the release that caused it.
BUILD_INFO = Gauge("djassa_build_info", "The running build", ["commit"])
BUILD_INFO.labels(commit=(os.getenv("RENDER_GIT_COMMIT") or "dev")[:7]).set(1)


def _published_paths(app) -> frozenset[str]:
    """The API's route templates, from its OpenAPI schema, built once."""
    paths = getattr(app.state, "published_paths", None)
    if paths is None:
        try:
            paths = frozenset(app.openapi().get("paths", {}))
        except Exception:
            paths = frozenset()
        app.state.published_paths = paths
    return paths


def route_label(request: Request) -> str:
    """The matched route's full template, or "unmatched" (404s, scanners).

    FastAPI leaves the route of an included router with its own path
    ("/venues/{venue_id}"), without the router's prefix. The prefix is taken
    back from the request path, and kept only when prefix + template is a
    published route: a label is always a template, never a raw URL.
    """
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if not template:
        return "unmatched"
    path = request.scope.get("path", "")
    regex = getattr(route, "path_regex", None)
    if regex is not None and not regex.fullmatch(path):
        for i in range(1, len(path)):
            if path[i] == "/" and regex.fullmatch(path[i:]):
                full = path[:i] + template
                if full in _published_paths(request.app):
                    return full
                break
    return template


def metrics_authorized(authorization: str | None) -> bool:
    token = os.getenv("METRICS_TOKEN")
    if not token:
        return os.getenv("DJASSA_ENV") is None
    if not authorization:
        return False
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer":
        supplied = credentials.strip()
    elif scheme.lower() == "basic":
        try:
            supplied = base64.b64decode(credentials.strip(), validate=True).decode().partition(":")[2]
        except (ValueError, UnicodeDecodeError):
            return False
    else:
        return False
    return hmac.compare_digest(supplied.encode(), token.encode())


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        line.update(getattr(record, "fields", {}))
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False)


def setup_logging() -> None:
    """Sends the app's loggers to stderr; JSON when `LOG_FORMAT=json`.

    Uvicorn configures its own loggers without propagating, so this does not
    print its lines twice.
    """
    handler = logging.StreamHandler(sys.stderr)
    if os.getenv("LOG_FORMAT") == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


async def observe_request(request: Request, call_next):
    """Times the request, records its metrics and writes its access line."""
    # Accept a well-formed id from the caller (a proxy, an app retry) so one
    # request can be followed end to end; otherwise make one.
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if 8 <= len(supplied) <= 64 and supplied.replace("-", "").isalnum() else uuid.uuid4().hex
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        # Also on an unhandled exception, so 500s are counted and logged.
        duration = time.perf_counter() - start
        route = route_label(request)
        record_request(request.method, route, status, duration)
        if route not in ("/health", "/metrics"):
            level = logging.ERROR if status >= 500 else logging.INFO
            access_log.log(
                level,
                "%s %s %s %.0fms",
                request.method,
                route,
                status,
                duration * 1000,
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": request.method,
                        "route": route,
                        "status": status,
                        "duration_ms": round(duration * 1000, 1),
                    }
                },
            )
