"""auth erase outbox: retry telling the auth service a person was erased

Revision ID: 0030_auth_erase_outbox
Revises: 0029_wallet_change
Create Date: 2026-11-20 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0030_auth_erase_outbox'
down_revision = '0029_wallet_change'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'auth_erase_outbox',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_sealed', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='pending'),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_auth_erase_outbox_id', 'auth_erase_outbox', ['id'])
    op.create_index('ix_auth_erase_outbox_next_attempt_at', 'auth_erase_outbox', ['next_attempt_at'])


def downgrade():
    op.drop_index('ix_auth_erase_outbox_next_attempt_at', table_name='auth_erase_outbox')
    op.drop_index('ix_auth_erase_outbox_id', table_name='auth_erase_outbox')
    op.drop_table('auth_erase_outbox')
