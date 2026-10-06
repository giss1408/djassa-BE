import os
import sys
import tempfile
from pathlib import Path

# Must run before `app` is imported: the engine is built at import time. Tests
# get a throwaway SQLite file so they can never touch a developer's database.
_tmp = Path(tempfile.mkdtemp(prefix="djassa-tests-")) / "test.db"
os.environ["DATABASE_URL"] = os.getenv("DJASSA_TEST_DATABASE_URL", f"sqlite+aiosqlite:///{_tmp}")
os.environ["DJASSA_SEED_SAMPLE"] = "1"
# The app refuses to start without these (production fails closed on missing
# secrets); tests get explicit throwaway values.
os.environ.setdefault("DJASSA_SECRET_KEY", "test-only-jwt-secret")
os.environ.setdefault("MOBILE_MONEY_SECRETS", "dev-secret")
# The whole suite reads the public catalogue from one address; its own limit
# is tested in test_public_catalogue.py.
os.environ.setdefault("PUBLIC_READ_RATE_LIMIT", "100000/minute")
os.environ.setdefault("MOBILE_MONEY_PROVIDER", "fake")
# No Redis in tests: an unreachable broker makes every `.delay()` retry for
# ~20s before the webhook falls back to inline processing.
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest_asyncio  # noqa: E402  (after the env setup above, on purpose)
from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402


# SQLite ignores foreign keys unless asked, so without this a broken reference
# passes in tests and fails with a 500 on Postgres in production.
@event.listens_for(Engine, "connect")
def _sqlite_enforce_foreign_keys(dbapi_connection, _record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    """Create the tables before every test.

    httpx's ASGITransport does not run the app's startup hook, which is where
    the schema is normally created, so without this a test only passed if an
    earlier one happened to create the tables. `create_all` is idempotent.
    """
    import app.models  # noqa: F401  registers the tables on Base.metadata
    from app.db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
