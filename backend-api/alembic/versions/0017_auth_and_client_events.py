"""Phone + OTP sign-in (users, codes, refresh tokens) and app error reports

Revision ID: 0017_auth_and_client_events
Revises: 0016_wave_accounts
Create Date: 2026-10-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0017_auth_and_client_events'
down_revision = '0016_wave_accounts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_e164', sa.String(length=16), nullable=False),
        sa.Column('roles', sa.String(length=64), nullable=False, server_default='customer'),
        sa.Column('disabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_phone_e164', 'users', ['phone_e164'], unique=True)

    op.create_table(
        'otp_challenges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_e164', sa.String(length=16), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_otp_challenges_id', 'otp_challenges', ['id'])
    op.create_index('ix_otp_challenges_phone_created', 'otp_challenges', ['phone_e164', 'created_at'])

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('family', sa.String(length=32), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('rotated_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_refresh_tokens_id', 'refresh_tokens', ['id'])
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index('ix_refresh_tokens_family', 'refresh_tokens', ['family'])

    op.create_table(
        'client_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('app', sa.String(length=16), nullable=False),
        sa.Column('app_version', sa.String(length=32), nullable=False),
        sa.Column('platform', sa.String(length=16), nullable=False),
        sa.Column('os_version', sa.String(length=64), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('message', sa.String(length=512), nullable=False),
        sa.Column('stack', sa.Text(), nullable=True),
        sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_client_events_id', 'client_events', ['id'])
    op.create_index('ix_client_events_fingerprint', 'client_events', ['fingerprint'])
    op.create_index('ix_client_events_app_received', 'client_events', ['app', 'received_at'])


def downgrade():
    op.drop_index('ix_client_events_app_received', table_name='client_events')
    op.drop_index('ix_client_events_fingerprint', table_name='client_events')
    op.drop_index('ix_client_events_id', table_name='client_events')
    op.drop_table('client_events')
    op.drop_index('ix_refresh_tokens_family', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_id', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('ix_otp_challenges_phone_created', table_name='otp_challenges')
    op.drop_index('ix_otp_challenges_id', table_name='otp_challenges')
    op.drop_table('otp_challenges')
    op.drop_index('ix_users_phone_e164', table_name='users')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_table('users')
