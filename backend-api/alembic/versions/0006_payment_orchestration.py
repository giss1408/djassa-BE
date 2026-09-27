"""add payment orchestration and reconciliation tables

Revision ID: 0006_payment_orchestration
Revises: 0005_support_requests
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_payment_orchestration"
down_revision = "0005_support_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payments", sa.Column("country_code", sa.String(length=2), nullable=False, server_default="CI"))
    op.add_column("payments", sa.Column("provider", sa.String(length=64), nullable=False, server_default="sandbox"))
    op.add_column("payments", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.add_column("payments", sa.Column("checkout_url", sa.String(length=1024), nullable=True))
    op.add_column("payments", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("payments", sa.Column("status", sa.String(length=32), nullable=False, server_default="created"))
    op.add_column("payments", sa.Column("provider_status", sa.String(length=32), nullable=True))
    op.add_column("payments", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("payments", sa.Column("created_by", sa.String(length=128), nullable=True))
    op.add_column("payments", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column("payments", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_payments_external_id", "payments", ["external_id"], unique=True)
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"], unique=True)
    op.create_index("ix_payments_created_by", "payments", ["created_by"])
    op.create_table(
        "payment_reconciliations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_status", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("raw_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_payment_reconciliations_payment_id", "payment_reconciliations", ["payment_id"])
    op.create_index("ix_payment_reconciliations_external_id", "payment_reconciliations", ["external_id"])
    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("external_id", sa.String(length=255), nullable=True, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "payment_disputes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("payment_disputes")
    op.drop_table("payment_refunds")
    op.drop_index("ix_payment_reconciliations_external_id", table_name="payment_reconciliations")
    op.drop_index("ix_payment_reconciliations_payment_id", table_name="payment_reconciliations")
    op.drop_table("payment_reconciliations")
    op.drop_index("ix_payments_created_by", table_name="payments")
    op.drop_index("ix_payments_idempotency_key", table_name="payments")
    op.drop_index("ix_payments_external_id", table_name="payments")
    for column in ("updated_at", "created_at", "created_by", "error_code", "provider_status", "status", "idempotency_key", "checkout_url", "external_id", "provider", "country_code"):
        op.drop_column("payments", column)