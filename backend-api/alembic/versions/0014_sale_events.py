"""One sale stream, with an evidence field; backfilled from both old ones

Revision ID: 0014_sale_events
Revises: 0013_export_audit
Create Date: 2026-09-29 00:00:00.000004

The backfill order matters and is the part to get right:

1. Create `sale_events`.
2. Confirmed payments (`customer_payments.status = 'succeeded'`) become
   `mobile_money_confirmed`. These already carry a venue, so they map cleanly.
3. Declared sales (`transactions`) become `cash_declared`, resolving the venue
   through `venues.merchant_id`, which is the bridge column that already exists.
4. Whatever step 3 cannot resolve is **quarantined, not guessed**. The retailer
   app posted a hardcoded `merchant_id = 1` and `/api/transactions` created a
   merchant row on demand for any unknown id, so a declared sale may belong to
   no real venue at all. Inventing a mapping would put one merchant's money in
   another's revenue history and, eventually, in a document shown to a lender.
   The count is printed so the number is known rather than discovered later.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0014_sale_events'
down_revision = '0013_export_audit'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sale_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=True, index=True),
        sa.Column('source', sa.String(length=24), nullable=False, index=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='recorded', index=True),
        sa.Column('amount', sa.Numeric(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='XOF'),
        sa.Column('type', sa.String(length=32), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('customer_id', sa.String(length=128), nullable=True, index=True),
        sa.Column('payment_id', sa.Integer(), sa.ForeignKey('customer_payments.id'), nullable=True, unique=True),
        sa.Column('loyalty_entry_id', sa.Integer(), sa.ForeignKey('loyalty_entries.id'), nullable=True),
        sa.Column('idempotency_key', sa.String(length=160), nullable=False, unique=True, index=True),
        sa.Column('idempotency_hash', sa.String(length=64), nullable=True),
        sa.Column('recorded_by', sa.String(length=128), nullable=True, index=True),
        sa.Column('legacy_merchant_id', sa.Integer(), nullable=True, index=True),
        sa.Column('legacy_transaction_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_sale_events_venue_occurred_at', 'sale_events', ['venue_id', 'occurred_at'])
    op.create_index('ix_sale_events_venue_source', 'sale_events', ['venue_id', 'source'])

    bind = op.get_bind()

    # --- Step 2: the confirmed stream -----------------------------------------
    #
    # `completed_at` is when the aggregator settled it; a succeeded payment
    # always has one, but fall back to `created_at` rather than write a NULL
    # into a NOT NULL column if some old row does not.
    bind.execute(sa.text("""
        INSERT INTO sale_events (
            venue_id, source, status, amount, currency, type,
            occurred_at, recorded_at, customer_id, payment_id, loyalty_entry_id,
            idempotency_key, recorded_by, created_at
        )
        SELECT
            p.venue_id,
            'mobile_money_confirmed',
            'recorded',
            p.amount,
            p.currency,
            'sale',
            COALESCE(p.completed_at, p.created_at),
            COALESCE(p.completed_at, p.created_at),
            p.customer_id,
            p.id,
            (SELECT e.id FROM loyalty_entries e WHERE e.payment_id = p.id),
            'pay:' || p.id,
            NULL,
            COALESCE(p.completed_at, p.created_at)
        FROM customer_payments p
        WHERE p.status = 'succeeded'
    """))

    # --- Steps 3 and 4: the declared stream, resolved or quarantined ----------
    #
    # One venue per merchant id: with several, there is no basis for choosing,
    # so the row is quarantined like an unmapped one. MIN(id) inside the
    # subquery would silently pick a winner.
    bind.execute(sa.text("""
        INSERT INTO sale_events (
            venue_id, source, status, amount, currency, type,
            occurred_at, recorded_at, idempotency_key, idempotency_hash,
            recorded_by, legacy_merchant_id, legacy_transaction_id, created_at
        )
        SELECT
            v.venue_id,
            'cash_declared',
            CASE WHEN v.venue_id IS NULL THEN 'quarantined' ELSE 'recorded' END,
            t.amount,
            t.currency,
            t.type,
            t.timestamp,
            t.timestamp,
            'legacy:' || t.id,
            t.idempotency_hash,
            t.user_id,
            t.merchant_id,
            t.id,
            t.timestamp
        FROM transactions t
        LEFT JOIN (
            SELECT merchant_id, MIN(id) AS venue_id, COUNT(*) AS n
            FROM venues
            WHERE merchant_id IS NOT NULL
            GROUP BY merchant_id
        ) v ON v.merchant_id = t.merchant_id AND v.n = 1
    """))

    quarantined = bind.execute(
        sa.text("SELECT COUNT(*) FROM sale_events WHERE status = 'quarantined'")
    ).scalar()
    total = bind.execute(sa.text("SELECT COUNT(*) FROM sale_events")).scalar()
    print(
        f"0014_sale_events: {total} sale events, of which {quarantined} quarantined "
        "(declared sales with no resolvable venue -- resolve by hand, do not sum them)"
    )


def downgrade():
    # `transactions` and `customer_payments` were never modified, so dropping
    # this table loses only the merged view, not the underlying records. Cash
    # sales recorded through POST /api/merchant/sales after the upgrade exist
    # ONLY here, though: check for them before rolling back.
    op.drop_index('ix_sale_events_venue_source', table_name='sale_events')
    op.drop_index('ix_sale_events_venue_occurred_at', table_name='sale_events')
    op.drop_table('sale_events')
