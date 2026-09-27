"""add progressive identity profiles

Revision ID: 0007_identity_profiles
Revises: 0006_payment_orchestration
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_identity_profiles"
down_revision = "0006_payment_orchestration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "identity_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("phone_e164", sa.String(length=16), nullable=False),
        sa.Column("operator", sa.String(length=64), nullable=False),
        sa.Column("verification_tier", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="tier_0_pending"),
        sa.Column("verification_provider", sa.String(length=128), nullable=True),
        sa.Column("attestation_reference", sa.String(length=255), nullable=True),
        sa.Column("consent_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_identity_profiles_user_id", "identity_profiles", ["user_id"], unique=True)


def downgrade():
    op.drop_index("ix_identity_profiles_user_id", table_name="identity_profiles")
    op.drop_table("identity_profiles")