"""QR payments: venue pay codes, venue owner, merchant payment requests

Revision ID: 0009_qr_payments
Revises: 0008_customer
Create Date: 2026-09-27 00:00:00.000001
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009_qr_payments'
down_revision = '0008_customer'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('venues', sa.Column('pay_code', sa.String(length=16), nullable=True))
    op.create_index('ix_venues_pay_code', 'venues', ['pay_code'], unique=True)
    op.add_column('venues', sa.Column('owner_username', sa.String(length=128), nullable=True))
    op.create_index('ix_venues_owner_username', 'venues', ['owner_username'])
    op.create_table(
        'payment_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(length=16), nullable=False, unique=True, index=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False, index=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('payment_id', sa.Integer(), sa.ForeignKey('customer_payments.id'), nullable=True),
    )


def downgrade():
    op.drop_table('payment_requests')
    op.drop_index('ix_venues_owner_username', table_name='venues')
    op.drop_column('venues', 'owner_username')
    op.drop_index('ix_venues_pay_code', table_name='venues')
    op.drop_column('venues', 'pay_code')
