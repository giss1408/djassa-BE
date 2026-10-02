"""Account recovery: code purposes, number changes, lost-number requests

Revision ID: 0018_account_recovery
Revises: 0017_auth_and_client_events
Create Date: 2026-10-02 00:00:00.000001
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0018_account_recovery'
down_revision = '0017_auth_and_client_events'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('otp_challenges') as batch:
        batch.add_column(sa.Column('purpose', sa.String(length=16), nullable=False, server_default='sign_in'))

    op.create_table(
        'recovery_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('old_phone_e164', sa.String(length=16), nullable=False),
        sa.Column('new_phone_e164', sa.String(length=16), nullable=False),
        sa.Column('details', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('decision_note', sa.String(length=500), nullable=True),
        sa.Column('decided_by', sa.String(length=128), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_recovery_requests_id', 'recovery_requests', ['id'])
    op.create_index('ix_recovery_requests_old_phone_e164', 'recovery_requests', ['old_phone_e164'])
    op.create_index('ix_recovery_requests_new_phone_e164', 'recovery_requests', ['new_phone_e164'])
    op.create_index('ix_recovery_requests_status', 'recovery_requests', ['status'])

    op.create_table(
        'account_number_changes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('old_phone_e164', sa.String(length=16), nullable=False),
        sa.Column('new_phone_e164', sa.String(length=16), nullable=False),
        sa.Column('method', sa.String(length=16), nullable=False),
        sa.Column('recovery_request_id', sa.Integer(), sa.ForeignKey('recovery_requests.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_account_number_changes_id', 'account_number_changes', ['id'])
    op.create_index('ix_account_number_changes_user_id', 'account_number_changes', ['user_id'])
    op.create_index('ix_account_number_changes_old_phone_e164', 'account_number_changes', ['old_phone_e164'])
    op.create_index('ix_account_number_changes_new_phone_e164', 'account_number_changes', ['new_phone_e164'])


def downgrade():
    op.drop_index('ix_account_number_changes_new_phone_e164', table_name='account_number_changes')
    op.drop_index('ix_account_number_changes_old_phone_e164', table_name='account_number_changes')
    op.drop_index('ix_account_number_changes_user_id', table_name='account_number_changes')
    op.drop_index('ix_account_number_changes_id', table_name='account_number_changes')
    op.drop_table('account_number_changes')
    op.drop_index('ix_recovery_requests_status', table_name='recovery_requests')
    op.drop_index('ix_recovery_requests_new_phone_e164', table_name='recovery_requests')
    op.drop_index('ix_recovery_requests_old_phone_e164', table_name='recovery_requests')
    op.drop_index('ix_recovery_requests_id', table_name='recovery_requests')
    op.drop_table('recovery_requests')
    with op.batch_alter_table('otp_challenges') as batch:
        batch.drop_column('purpose')
