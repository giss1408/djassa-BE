"""Sold runs of the featured deal slot, so a placement expires and can be invoiced

Revision ID: 0011_deal_placements
Revises: 0010_deals
Create Date: 2026-09-29 00:00:00.000001
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0011_deal_placements'
down_revision = '0010_deals'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deal_placements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=False, index=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='XOF'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='reserved', index=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('payment_reference', sa.String(length=64), nullable=True),
        sa.Column('created_by', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_deal_placements_window', 'deal_placements', ['starts_at', 'ends_at'])

    # Deals featured by hand before placements existed keep running, but there
    # is no commercial record to back-fill them with: an admin must sell them a
    # placement or they leave the carousel at the next expiry sweep.


def downgrade():
    op.drop_index('ix_deal_placements_window', table_name='deal_placements')
    op.drop_table('deal_placements')
