"""Wallet change process: requests, trail, and the date a wallet became active (first-week cap)

Revision ID: 0029_wallet_change
Revises: 0028_pilot_merchants
Create Date: 2026-11-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0029_wallet_change'
down_revision = '0028_pilot_merchants'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('venues', sa.Column('wallet_active_since', sa.DateTime(), nullable=True))
    op.create_table(
        'wallet_changes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        sa.Column('account', sa.String(length=32), nullable=False),
        sa.Column('prev_provider', sa.String(length=16), nullable=True),
        sa.Column('prev_account', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('requested_by', sa.String(length=128), nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=True),
        sa.Column('code_expires_at', sa.DateTime(), nullable=True),
        sa.Column('code_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('code_sent_by', sa.String(length=128), nullable=True),
        sa.Column('code_sent_at', sa.DateTime(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('activates_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('activated_by', sa.String(length=128), nullable=True),
        sa.Column('activation_mode', sa.String(length=16), nullable=True),
        sa.Column('call_note', sa.Text(), nullable=True),
        sa.Column('frozen_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.String(length=128), nullable=True),
        sa.Column('resolved_reason', sa.String(length=255), nullable=True),
    )
    op.create_index('ix_wallet_changes_venue_id', 'wallet_changes', ['venue_id'])
    op.create_index('ix_wallet_changes_status', 'wallet_changes', ['status'])
    op.create_table(
        'wallet_change_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('change_id', sa.Integer(), sa.ForeignKey('wallet_changes.id'), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('actor', sa.String(length=128), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('detail', sa.String(length=255), nullable=True),
    )
    op.create_index('ix_wallet_change_events_change_id', 'wallet_change_events', ['change_id'])


def downgrade():
    op.drop_table('wallet_change_events')
    op.drop_table('wallet_changes')
    op.drop_column('venues', 'wallet_active_since')
