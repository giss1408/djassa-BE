"""Wave option B: merchants' own Wave Business accounts, and Wave payment fields

Revision ID: 0016_wave_accounts
Revises: 0015_venue_location
Create Date: 2026-09-30 00:00:00.000006
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0016_wave_accounts'
down_revision = '0015_venue_location'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'wave_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('api_key_sealed', sa.Text(), nullable=False),
        sa.Column('api_key_hint', sa.String(length=8), nullable=False),
        sa.Column('webhook_secret_sealed', sa.Text(), nullable=True),
        sa.Column('webhook_token', sa.String(length=48), nullable=False),
        sa.Column('connected_by', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_event_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_wave_accounts_venue_id', 'wave_accounts', ['venue_id'], unique=True)
    op.create_index('ix_wave_accounts_webhook_token', 'wave_accounts', ['webhook_token'], unique=True)
    op.add_column('customer_payments', sa.Column('checkout_url', sa.String(length=512), nullable=True))
    op.add_column('customer_payments', sa.Column('external_transaction_id', sa.String(length=64), nullable=True))
    op.create_index(
        'ix_customer_payments_external_transaction_id', 'customer_payments', ['external_transaction_id']
    )


def downgrade():
    op.drop_index('ix_customer_payments_external_transaction_id', table_name='customer_payments')
    op.drop_column('customer_payments', 'external_transaction_id')
    op.drop_column('customer_payments', 'checkout_url')
    op.drop_index('ix_wave_accounts_webhook_token', table_name='wave_accounts')
    op.drop_index('ix_wave_accounts_venue_id', table_name='wave_accounts')
    op.drop_table('wave_accounts')
