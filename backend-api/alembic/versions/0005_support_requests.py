"""add localized support requests

Revision ID: 0005_support_requests
Revises: 0004_transaction_idempotency
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_support_requests"
down_revision = "0004_transaction_idempotency"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "support_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_support_requests_user_created_at", "support_requests", ["user_id", "created_at"])
    op.create_index("ix_support_requests_country_status", "support_requests", ["country_code", "status"])


def downgrade():
    op.drop_index("ix_support_requests_country_status", table_name="support_requests")
    op.drop_index("ix_support_requests_user_created_at", table_name="support_requests")
    op.drop_table("support_requests")