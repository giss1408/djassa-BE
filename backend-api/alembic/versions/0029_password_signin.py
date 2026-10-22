"""Password sign-in: password hashes, account checks and admin actions

Revision ID: 0029_password_signin
Revises: 0028_pilot_merchants
Create Date: 2026-10-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0029_password_signin'
down_revision = '0028_pilot_merchants'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('password_hash', sa.String(length=255), nullable=True))
        batch.add_column(sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('phone_verified_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('failed_logins', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('locked_until', sa.DateTime(), nullable=True))

    op.create_table(
        'account_checks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('new_phone_e164', sa.String(length=16), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('secret_hash', sa.String(length=64), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('sent_by', sa.String(length=128), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('team_created', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('consent_version', sa.String(length=64), nullable=True),
    )
    op.create_index('ix_account_checks_id', 'account_checks', ['id'])
    op.create_index('ix_account_checks_user_kind_status', 'account_checks', ['user_id', 'kind', 'status'])

    op.create_table(
        'admin_actions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('admin_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('check_id', sa.Integer(), sa.ForeignKey('account_checks.id'), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_admin_actions_id', 'admin_actions', ['id'])

    with op.batch_alter_table('recovery_requests') as batch:
        batch.add_column(sa.Column('filer_user_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_recovery_requests_filer_user_id'), nullable=True))

    # Existing users proved their number by SMS: their sessions keep working.
    op.execute("UPDATE users SET phone_verified_at = COALESCE(last_login_at, created_at)")


def downgrade():
    with op.batch_alter_table('recovery_requests') as batch:
        batch.drop_column('filer_user_id')
    op.drop_index('ix_admin_actions_id', table_name='admin_actions')
    op.drop_table('admin_actions')
    op.drop_index('ix_account_checks_user_kind_status', table_name='account_checks')
    op.drop_index('ix_account_checks_id', table_name='account_checks')
    op.drop_table('account_checks')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('locked_until')
        batch.drop_column('failed_logins')
        batch.drop_column('phone_verified_at')
        batch.drop_column('must_change_password')
        batch.drop_column('password_hash')
