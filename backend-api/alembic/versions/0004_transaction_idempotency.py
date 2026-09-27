"""add transaction idempotency fields

Revision ID: 0004_transaction_idempotency
Revises: 0003_query_indexes
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_transaction_idempotency"
down_revision = "0003_query_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transactions", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("transactions", sa.Column("idempotency_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_transactions_idempotency_key", "transactions", ["idempotency_key"], unique=True)


def downgrade():
    op.drop_index("ix_transactions_idempotency_key", table_name="transactions")
    op.drop_column("transactions", "idempotency_hash")
    op.drop_column("transactions", "idempotency_key")