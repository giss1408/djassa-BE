"""Audit every consented export: who took what, when, under which consent

Revision ID: 0013_export_audit
Revises: 0012_merchant_billing
Create Date: 2026-09-29 00:00:00.000003
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0013_export_audit'
down_revision = '0012_merchant_billing'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'export_audits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('exported_by', sa.String(length=128), nullable=False, index=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=True, index=True),
        sa.Column('merchant_id', sa.Integer(), nullable=True, index=True),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('scope', sa.String(length=255), nullable=True),
        sa.Column('consent_id', sa.Integer(), sa.ForeignKey('consents.id'), nullable=True),
        sa.Column('subject_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('period_start', sa.DateTime(), nullable=True),
        sa.Column('period_end', sa.DateTime(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_export_audits_occurred_at', 'export_audits', ['occurred_at'])


def downgrade():
    op.drop_index('ix_export_audits_occurred_at', table_name='export_audits')
    op.drop_table('export_audits')
