from fastapi import FastAPI, Request
from .api import payments, auth, transactions, export, tontine, webhooks, config, support, identity
from .api import customer, payment_requests, deals, billing, sales, statements, counter_loyalty, venue_location, wave, client_events, account, onboarding, media
from .graphql_api import router as graphql_router
from .db import engine, Base
from .seed import seed_sample_data, seeding_enabled
from starlette.middleware import Middleware
from slowapi.middleware import SlowAPIMiddleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .rate_limiter import limiter
from .metrics import record_request
import time
import os

# OpenTelemetry tracing setup (OTLP exporter)
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Configure tracer provider with basic service resource
resource = Resource.create({"service.name": "djassa-backend"})
provider = TracerProvider(resource=resource)
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    otlp_exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)

# Middleware stack
middleware = [
    Middleware(SlowAPIMiddleware),
    Middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Signature"],
    ),
]


app = FastAPI(title="djassa API", middleware=middleware)


@app.on_event("startup")
async def startup():
    # Production schemas come from Alembic migrations. The local SQLite dev
    # database is created and seeded here so the apps work out of the box;
    # seeding_enabled() is off for any non-SQLite database unless asked for.
    if seeding_enabled():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_sample_data()

# instrument frameworks after app creation
FastAPIInstrumentor.instrument_app(app)

# instrument SQLAlchemy engine
try:
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
except Exception:
    pass

# security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.state.limiter = limiter


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    # normalize path for metrics
    path = request.url.path
    record_request(request.method, path, response.status_code, duration)
    return response

app.include_router(auth.router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(onboarding.router, prefix="/api")
app.include_router(media.router, prefix="/api")

# Shop media on local disk (development). In production MEDIA_STORAGE=r2 and
# the files are served by Cloudflare, never by the API.
@app.get("/media/{key:path}", include_in_schema=False)
async def local_media(key: str):
    from pathlib import Path

    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    from .services.media_storage import IMMUTABLE, local_dir

    if os.getenv("MEDIA_STORAGE", "local") != "local":
        raise HTTPException(status_code=404)
    root = Path(local_dir()).resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, headers={"Cache-Control": IMMUTABLE})
app.include_router(payments.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(tontine.router, prefix="/api")
app.include_router(customer.router, prefix="/api")
app.include_router(payment_requests.router, prefix="/api")
app.include_router(deals.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(sales.router, prefix="/api")
app.include_router(counter_loyalty.router, prefix="/api")
app.include_router(venue_location.router, prefix="/api")
app.include_router(wave.router, prefix="/api")
app.include_router(wave.public_router)
app.include_router(statements.router, prefix="/api")
app.include_router(webhooks.router)
app.include_router(config.router, prefix="/api")
app.include_router(support.router, prefix="/api")
app.include_router(identity.router, prefix="/api")
app.include_router(client_events.router, prefix="/api")
app.include_router(graphql_router, prefix="/graphql")

# Expose /metrics endpoint for Prometheus to scrape (compose local)
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST


@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    async with engine.connect() as connection:
        await connection.exec_driver_sql("SELECT 1")
    return {"ready": True}
