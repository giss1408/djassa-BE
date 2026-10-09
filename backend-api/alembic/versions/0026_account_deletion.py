"""Account deletion requests from merchants, cashiers and field agents

Revision ID: 0026_account_deletion
Revises: 0025_layaway
Create Date: 2026-10-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0026_account_deletion'
down_revision = '0025_layaway'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'account_deletion_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_e164', sa.String(length=16), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('decision_note', sa.String(length=500), nullable=True),
        sa.Column('decided_by', sa.String(length=128), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_account_deletion_requests_id', 'account_deletion_requests', ['id'])
    op.create_index('ix_account_deletion_requests_phone_e164', 'account_deletion_requests', ['phone_e164'])
    op.create_index('ix_account_deletion_requests_status', 'account_deletion_requests', ['status'])


def downgrade():
    op.drop_index('ix_account_deletion_requests_status', table_name='account_deletion_requests')
    op.drop_index('ix_account_deletion_requests_phone_e164', table_name='account_deletion_requests')
    op.drop_index('ix_account_deletion_requests_id', table_name='account_deletion_requests')
    op.drop_table('account_deletion_requests')
