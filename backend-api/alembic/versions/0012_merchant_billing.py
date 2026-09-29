"""Merchant subscriptions and append-only billing events

Revision ID: 0012_merchant_billing
Revises: 0011_deal_placements
Create Date: 2026-09-29 00:00:00.000002
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0012_merchant_billing'
down_revision = '0011_deal_placements'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'merchant_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('plan', sa.String(length=16), nullable=False, server_default='starter'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='trialing', index=True),
        sa.Column('amount', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='XOF'),
        sa.Column('period', sa.String(length=16), nullable=False, server_default='monthly'),
        sa.Column('current_period_start', sa.DateTime(), nullable=True),
        sa.Column('current_period_end', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(
        'ix_merchant_subscriptions_venue_status', 'merchant_subscriptions', ['venue_id', 'status']
    )

    op.create_table(
        'billing_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('merchant_subscriptions.id'), nullable=False, index=True),
        sa.Column('kind', sa.String(length=16), nullable=False, index=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='XOF'),
        sa.Column('payment_reference', sa.String(length=64), nullable=True),
        sa.Column('period_start', sa.DateTime(), nullable=True),
        sa.Column('period_end', sa.DateTime(), nullable=True),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('recorded_by', sa.String(length=128), nullable=False),
    )
    op.create_index(
        'ix_billing_events_subscription_occurred', 'billing_events', ['subscription_id', 'occurred_at']
    )

    # No back-fill: venues with no subscription row read as starter, which is
    # what every pilot merchant is until someone sells them a plan.


def downgrade():
    op.drop_index('ix_billing_events_subscription_occurred', table_name='billing_events')
    op.drop_table('billing_events')
    op.drop_index('ix_merchant_subscriptions_venue_status', table_name='merchant_subscriptions')
    op.drop_table('merchant_subscriptions')
