"""Loyalty consents: no phone number is tied to a sale without one

Revision ID: 0023_loyalty_consents
Revises: 0022_enrollment_roles
Create Date: 2026-10-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0023_loyalty_consents'
down_revision = '0022_enrollment_roles'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'loyalty_consents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.String(length=128), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=True),
        sa.Column('consent_version', sa.String(length=64), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.Column('withdrawn_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_loyalty_consents_id', 'loyalty_consents', ['id'])
    op.create_index('ix_loyalty_consents_customer_id', 'loyalty_consents', ['customer_id'], unique=True)


def downgrade():
    op.drop_index('ix_loyalty_consents_customer_id', table_name='loyalty_consents')
    op.drop_index('ix_loyalty_consents_id', table_name='loyalty_consents')
    op.drop_table('loyalty_consents')
