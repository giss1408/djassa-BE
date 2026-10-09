"""Migration 0014: backfilling the merged stream without inventing a mapping.

The risk this covers is specific. The retailer app posted a hardcoded
`merchant_id = 1` and `/api/transactions` created a merchant row on demand for
any unknown id, so a declared sale may belong to no real venue at all. A
migration that "resolved" those would put one merchant's money into another's
revenue history and, eventually, into a signed document shown to a lender.

Run against the real Alembic chain on a throwaway SQLite file rather than
against `create_all`, because it is the SQL in the migration that is under test.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
PRIOR_REVISION = "0013_export_audit"
REVISION = "0014_sale_events"


def _alembic(db_path: Path, *args: str):
    """Run alembic against `db_path` in a subprocess.

    A subprocess rather than the API because `app.db` builds its engine from the
    environment at import time, and the test session has already imported it
    pointing somewhere else.
    """
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "FIDELIA_SECRET_KEY": "test-only-jwt-secret",
        "MOBILE_MONEY_SECRETS": "dev-secret",
        # Seeding would add venues and change the counts under test.
        "FIDELIA_SEED_SAMPLE": "0",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def legacy_db():
    """A database at 0013 holding both old streams, including unmappable rows."""
    import sqlite3

    directory = Path(tempfile.mkdtemp(prefix="fidelia-migration-"))
    db_path = directory / "legacy.db"

    upgraded = _alembic(db_path, "upgrade", PRIOR_REVISION)
    assert upgraded.returncode == 0, upgraded.stderr

    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        -- Two merchants, only one of which a venue points at.
        INSERT INTO merchants (id, name) VALUES (1, 'merchant-1'), (7, 'Real merchant');

        INSERT INTO venues (id, category, name, commune, merchant_id, points_per_100, is_sample)
        VALUES (10, 'maquis', 'Mapped venue', 'Cocody', 7, 1, 0);
        -- A venue with no merchant id at all, so nothing can resolve to it.
        INSERT INTO venues (id, category, name, commune, merchant_id, points_per_100, is_sample)
        VALUES (11, 'superette', 'Unlinked venue', 'Yopougon', NULL, 1, 0);

        -- Declared sales: one resolvable, two not (merchant 1 is the app's
        -- hardcoded placeholder; merchant 99 was auto-created on demand).
        INSERT INTO transactions (id, merchant_id, user_id, amount, currency, type, timestamp)
        VALUES (1, 7, 'demo', 5000, 'XOF', 'sale', '2026-09-01 10:00:00'),
               (2, 1, 'demo', 1500, 'XOF', 'sale', '2026-09-02 11:00:00'),
               (3, 99, 'demo', 2500, 'XOF', 'sale', '2026-09-03 12:00:00');

        -- Confirmed payments: only the succeeded one is a sale.
        INSERT INTO customer_payments
            (id, customer_id, venue_id, amount, currency, wallet_provider, payer_msisdn,
             status, idempotency_key, points_awarded, created_at, completed_at)
        VALUES (1, 'client', 10, 3000, 'XOF', 'wave', '+2250700000001',
                'succeeded', 'legacy-key-1', 30, '2026-09-04 09:00:00', '2026-09-04 09:00:05'),
               (2, 'client', 10, 8000, 'XOF', 'wave', '+2250700000002',
                'failed', 'legacy-key-2', 0, '2026-09-05 09:00:00', '2026-09-05 09:00:05'),
               (3, 'client', 10, 4000, 'XOF', 'orange', '+2250700000003',
                'pending', 'legacy-key-3', 0, '2026-09-06 09:00:00', NULL);

        INSERT INTO loyalty_entries (id, customer_id, venue_id, points, reason, payment_id, created_at)
        VALUES (1, 'client', 10, 30, 'payment', 1, '2026-09-04 09:00:05');
        """
    )
    connection.commit()
    connection.close()
    yield db_path, connection


def _rows(db_path: Path, sql: str):
    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def test_the_backfill_labels_each_stream_and_quarantines_what_it_cannot_resolve(legacy_db):
    db_path, _ = legacy_db
    result = _alembic(db_path, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr

    events = _rows(
        db_path,
        "SELECT source, status, amount, venue_id, legacy_merchant_id, legacy_transaction_id, payment_id "
        "FROM sale_events ORDER BY source, amount",
    )
    by_source_status: dict[tuple[str, str], list] = {}
    for source, status, amount, venue_id, legacy_merchant, legacy_txn, payment_id in events:
        by_source_status.setdefault((source, status), []).append(
            (float(amount), venue_id, legacy_merchant, legacy_txn, payment_id)
        )

    # Only the succeeded payment became a confirmed event. A failed or pending
    # one is not a sale.
    confirmed = by_source_status[("mobile_money_confirmed", "recorded")]
    assert len(confirmed) == 1
    assert confirmed[0][0] == 3000.0
    assert confirmed[0][1] == 10
    assert confirmed[0][4] == 1, "the confirmed event links back to its payment"

    # The declared sale whose merchant a venue claims resolved to that venue.
    resolved = by_source_status[("cash_declared", "recorded")]
    assert len(resolved) == 1
    assert resolved[0][0] == 5000.0
    assert resolved[0][1] == 10

    # The two unmappable ones are quarantined with no venue, and their original
    # merchant id is kept so a human can resolve them.
    quarantined = sorted(by_source_status[("cash_declared", "quarantined")])
    assert [q[0] for q in quarantined] == [1500.0, 2500.0]
    assert all(q[1] is None for q in quarantined), "a quarantined row is attached to nobody"
    assert sorted(q[2] for q in quarantined) == [1, 99]
    assert sorted(q[3] for q in quarantined) == [2, 3]


def test_the_loyalty_link_is_carried_over(legacy_db):
    """The point of the merged stream: one row ties payment, venue and points."""
    db_path, _ = legacy_db
    assert _alembic(db_path, "upgrade", REVISION).returncode == 0

    linked = _rows(
        db_path,
        "SELECT loyalty_entry_id FROM sale_events WHERE source = 'mobile_money_confirmed'",
    )
    assert linked == [(1,)]


def test_quarantined_rows_are_excluded_from_every_total(legacy_db):
    """A recorded amount belonging to nobody must not become someone's revenue."""
    db_path, _ = legacy_db
    assert _alembic(db_path, "upgrade", REVISION).returncode == 0

    recorded = _rows(
        db_path, "SELECT COALESCE(SUM(amount), 0) FROM sale_events WHERE status = 'recorded'"
    )[0][0]
    # 3000 confirmed + 5000 resolved declared. The 1500 and 2500 are excluded.
    assert float(recorded) == 8000.0

    for_venue_10 = _rows(
        db_path,
        "SELECT COALESCE(SUM(amount), 0) FROM sale_events WHERE venue_id = 10 AND status = 'recorded'",
    )[0][0]
    assert float(for_venue_10) == 8000.0


def test_an_ambiguous_merchant_is_quarantined_rather_than_assigned(legacy_db):
    """Two venues sharing a merchant id give no basis for choosing between them.

    Picking one (MIN(id), say) would silently credit one merchant with another's
    sales -- the exact failure quarantine exists to prevent.
    """
    import sqlite3

    db_path, _ = legacy_db
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        -- A second venue claiming merchant 7, making it ambiguous.
        INSERT INTO venues (id, category, name, commune, merchant_id, points_per_100, is_sample)
        VALUES (12, 'maquis', 'Rival claimant', 'Marcory', 7, 1, 0);
        """
    )
    connection.commit()
    connection.close()

    assert _alembic(db_path, "upgrade", REVISION).returncode == 0

    row = _rows(
        db_path,
        "SELECT status, venue_id FROM sale_events WHERE legacy_transaction_id = 1",
    )
    assert row == [("quarantined", None)]


def test_the_migration_rolls_forward_and_back(legacy_db):
    """MIGRATIONS.md requires a tested downgrade."""
    db_path, _ = legacy_db
    assert _alembic(db_path, "upgrade", REVISION).returncode == 0
    assert _rows(db_path, "SELECT COUNT(*) FROM sale_events")[0][0] == 4

    down = _alembic(db_path, "downgrade", PRIOR_REVISION)
    assert down.returncode == 0, down.stderr
    tables = {r[0] for r in _rows(db_path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "sale_events" not in tables
    # The underlying records were never touched, so nothing was lost.
    assert _rows(db_path, "SELECT COUNT(*) FROM transactions")[0][0] == 3
    assert _rows(db_path, "SELECT COUNT(*) FROM customer_payments")[0][0] == 3

    # And forward again, with the same result: the backfill is not one-shot.
    assert _alembic(db_path, "upgrade", REVISION).returncode == 0
    assert _rows(db_path, "SELECT COUNT(*) FROM sale_events")[0][0] == 4


def test_the_quarantine_count_is_reported_not_swallowed(legacy_db):
    """A number nobody printed is a number nobody knows."""
    db_path, _ = legacy_db
    result = _alembic(db_path, "upgrade", REVISION)
    assert result.returncode == 0, result.stderr
    assert "2 quarantined" in result.stdout, result.stdout
