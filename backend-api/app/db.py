import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event
import time
from .metrics import record_db_query

def normalize_database_url(raw: str) -> tuple[str, dict]:
    """Accept a hosted Postgres URL as the provider shows it, for asyncpg.

    Neon (and Render, Supabase...) hand out `postgresql://...?sslmode=require
    &channel_binding=require`. asyncpg needs the `postgresql+asyncpg` driver
    prefix, spells TLS as `ssl=require`, and rejects libpq-only options such as
    `channel_binding`. Returns the URL and any `connect_args` it implies.

    Neon's pooled endpoint (host contains `-pooler`) runs PgBouncer in
    transaction mode, which breaks asyncpg's prepared-statement cache; the cache
    is turned off there. The direct endpoint needs nothing special.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    url = raw.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
    if not url.startswith("postgresql+asyncpg://"):
        return url, {}

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode and sslmode != "disable" and "ssl" not in query:
        query["ssl"] = "require"
    connect_args = {}
    if "-pooler" in (parts.hostname or ""):
        query.setdefault("prepared_statement_cache_size", "0")
        connect_args["statement_cache_size"] = 0
    return urlunsplit(parts._replace(query=urlencode(query))), connect_args


DATABASE_URL, _CONNECT_ARGS = normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
)

if DATABASE_URL.startswith("postgresql"):
    # Serverless Postgres (Neon) closes idle connections when it scales to
    # zero; pre-ping replaces a dead pooled connection instead of failing the
    # first request after a quiet period.
    engine = create_async_engine(
        DATABASE_URL, future=True, pool_pre_ping=True, pool_recycle=300, connect_args=_CONNECT_ARGS
    )
else:
    engine = create_async_engine(DATABASE_URL, future=True)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# SQLAlchemy query instrumentation for async engine
@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    try:
        duration = time.time() - context._query_start_time
        record_db_query(statement, duration)
    except Exception:
        pass
