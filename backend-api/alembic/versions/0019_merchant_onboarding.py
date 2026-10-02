"""Merchant onboarding: points-only Wave connections and partner requests

Revision ID: 0019_merchant_onboarding
Revises: 0018_account_recovery
Create Date: 2026-10-02 00:00:00.000002
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0019_merchant_onboarding'
down_revision = '0018_account_recovery'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('wave_accounts') as batch:
        batch.alter_column('api_key_sealed', existing_type=sa.Text(), nullable=True)
        batch.alter_column('api_key_hint', existing_type=sa.String(length=8), nullable=True)

    op.create_table(
        'partner_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_e164', sa.String(length=16), nullable=False),
        sa.Column('country_code', sa.String(length=2), nullable=False, server_default='CI'),
        sa.Column('contact_name', sa.String(length=120), nullable=False),
        sa.Column('shop_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('commune', sa.String(length=64), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('wallet_provider', sa.String(length=16), nullable=True),
        sa.Column('wallet_number', sa.String(length=16), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=True),
        sa.Column('decision_note', sa.String(length=500), nullable=True),
        sa.Column('decided_by', sa.String(length=128), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_partner_requests_id', 'partner_requests', ['id'])
    op.create_index('ix_partner_requests_phone_e164', 'partner_requests', ['phone_e164'])
    op.create_index('ix_partner_requests_status', 'partner_requests', ['status'])


def downgrade():
    op.drop_index('ix_partner_requests_status', table_name='partner_requests')
    op.drop_index('ix_partner_requests_phone_e164', table_name='partner_requests')
    op.drop_index('ix_partner_requests_id', table_name='partner_requests')
    op.drop_table('partner_requests')
    # Points-only connections have no key; they cannot survive the old schema.
    op.execute("DELETE FROM wave_accounts WHERE api_key_sealed IS NULL")
    with op.batch_alter_table('wave_accounts') as batch:
        batch.alter_column('api_key_hint', existing_type=sa.String(length=8), nullable=False)
        batch.alter_column('api_key_sealed', existing_type=sa.Text(), nullable=False)
