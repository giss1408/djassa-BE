"""customer side: venues, on-duty pharmacies, customer payments, loyalty

Revision ID: 0003_customer
Revises: 0002_tontine
Create Date: 2026-09-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_customer'
down_revision = '0002_tontine'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'venues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('category', sa.String(length=32), nullable=False, index=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('commune', sa.String(length=64), nullable=False, index=True),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('latitude', sa.Numeric(), nullable=True),
        sa.Column('longitude', sa.Numeric(), nullable=True),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('specialties', sa.String(length=255), nullable=True),
        sa.Column('opening_hours', sa.String(length=255), nullable=True),
        sa.Column('merchant_id', sa.Integer(), sa.ForeignKey('merchants.id'), nullable=True),
        sa.Column('payout_provider', sa.String(length=16), nullable=True),
        sa.Column('payout_account', sa.String(length=32), nullable=True),
        sa.Column('points_per_100', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_sample', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        'pharmacy_duties',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('starts_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('ends_at', sa.DateTime(), nullable=False, index=True),
    )
    op.create_table(
        'customer_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.String(length=128), nullable=False, index=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('wallet_provider', sa.String(length=16), nullable=False),
        sa.Column('payer_msisdn', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, index=True),
        sa.Column('failure_reason', sa.String(length=255), nullable=True),
        sa.Column('provider_reference', sa.String(length=64), nullable=True, index=True),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False, unique=True),
        sa.Column('points_awarded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'loyalty_rewards',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('cost_points', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        'loyalty_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.String(length=128), nullable=False, index=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=16), nullable=False),
        sa.Column('payment_id', sa.Integer(), sa.ForeignKey('customer_payments.id'), nullable=True, unique=True),
        sa.Column('reward_id', sa.Integer(), sa.ForeignKey('loyalty_rewards.id'), nullable=True),
        sa.Column('voucher_code', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('loyalty_entries')
    op.drop_table('loyalty_rewards')
    op.drop_table('customer_payments')
    op.drop_table('pharmacy_duties')
    op.drop_table('venues')
