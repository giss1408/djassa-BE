"""add indexes for ownership and time-ordered queries

Revision ID: 0003_query_indexes
Revises: 0002_tontine
"""
from alembic import op

revision = "0003_query_indexes"
down_revision = "0002_tontine"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_transactions_merchant_timestamp",
        "transactions",
        ["merchant_id", "timestamp"],
    )
    op.create_index(
        "ix_transactions_merchant_user_timestamp",
        "transactions",
        ["merchant_id", "user_id", "timestamp"],
    )
    op.create_index(
        "ix_consents_user_merchant_scope",
        "consents",
        ["user_id", "merchant_id", "scope"],
    )
    op.create_index(
        "ix_tontine_members_group_user_active",
        "tontine_members",
        ["group_id", "user_id", "active"],
    )
    op.create_index(
        "ix_contributions_group_member_paid_at",
        "tontine_contributions",
        ["group_id", "member_id", "paid_at"],
    )


def downgrade():
    op.drop_index("ix_contributions_group_member_paid_at", table_name="tontine_contributions")
    op.drop_index("ix_tontine_members_group_user_active", table_name="tontine_members")
    op.drop_index("ix_consents_user_merchant_scope", table_name="consents")
    op.drop_index("ix_transactions_merchant_user_timestamp", table_name="transactions")
    op.drop_index("ix_transactions_merchant_timestamp", table_name="transactions")