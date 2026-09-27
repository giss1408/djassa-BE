import os
import sys
import tempfile
from pathlib import Path

# Must run before `app` is imported: the engine is built at import time. Tests
# get a throwaway SQLite file so they can never touch a developer's database.
_tmp = Path(tempfile.mkdtemp(prefix="djassa-tests-")) / "test.db"
os.environ["DATABASE_URL"] = os.getenv("DJASSA_TEST_DATABASE_URL", f"sqlite+aiosqlite:///{_tmp}")
os.environ["DJASSA_SEED_SAMPLE"] = "1"
os.environ.setdefault("PAYMENT_PROVIDER", "fake")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
