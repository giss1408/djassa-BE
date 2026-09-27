"""Deals ("bons plans") published by venues, with an admin-only featured slot

Revision ID: 0010_deals
Revises: 0009_qr_payments
Create Date: 2026-09-27 00:00:00.000002
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_deals'
down_revision = '0009_qr_payments'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('discount_percent', sa.Integer(), nullable=True),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('original_price', sa.Integer(), nullable=True),
        sa.Column('starts_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('ends_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('is_featured', sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('deals')
