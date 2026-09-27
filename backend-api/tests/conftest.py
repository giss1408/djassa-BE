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
os.environ.setdefault("MOBILE_MONEY_PROVIDER", "fake")
# No Redis in tests: an unreachable broker makes every `.delay()` retry for
# ~20s before the webhook falls back to inline processing.
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest_asyncio  # noqa: E402  (after the env setup above, on purpose)


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
