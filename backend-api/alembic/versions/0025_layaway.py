"""Layaway: pay for one good in several installments, per-venue switch

Revision ID: 0025_layaway
Revises: 0024_deal_ribbon
Create Date: 2026-10-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0025_layaway'
down_revision = '0024_deal_ribbon'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('venues') as batch:
        batch.add_column(sa.Column('layaway_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        'layaway_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('customer_id', sa.String(length=128), nullable=False),
        sa.Column('item', sa.String(length=120), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='XOF'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='open'),
        sa.Column('due_by', sa.DateTime(), nullable=False),
        sa.Column('terms_version', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('sale_event_id', sa.Integer(), sa.ForeignKey('sale_events.id'), nullable=True, unique=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_by', sa.String(length=128), nullable=True),
        sa.Column('cancel_reason', sa.String(length=255), nullable=True),
        sa.Column('refunded_amount', sa.Integer(), nullable=True),
    )
    op.create_index('ix_layaway_plans_id', 'layaway_plans', ['id'])
    op.create_index('ix_layaway_plans_venue_id', 'layaway_plans', ['venue_id'])
    op.create_index('ix_layaway_plans_customer_id', 'layaway_plans', ['customer_id'])
    op.create_index('ix_layaway_plans_status', 'layaway_plans', ['status'])
    op.create_index('ix_layaway_plans_venue_status', 'layaway_plans', ['venue_id', 'status'])

    op.create_table(
        'layaway_installments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('layaway_plans.id'), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=24), nullable=False),
        sa.Column('idempotency_key', sa.String(length=160), nullable=False),
        sa.Column('recorded_by', sa.String(length=128), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_layaway_installments_id', 'layaway_installments', ['id'])
    op.create_index('ix_layaway_installments_plan_id', 'layaway_installments', ['plan_id'])
    op.create_index('ix_layaway_installments_idempotency_key', 'layaway_installments', ['idempotency_key'], unique=True)


def downgrade():
    op.drop_table('layaway_installments')
    op.drop_table('layaway_plans')
    with op.batch_alter_table('venues') as batch:
        batch.drop_column('layaway_enabled')
