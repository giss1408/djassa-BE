"""Drop otp_challenges: sign-in codes by SMS are gone

Revision ID: 0030_drop_otp_challenges
Revises: 0029_password_signin
Create Date: 2026-10-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0030_drop_otp_challenges'
down_revision = '0029_password_signin'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('ix_otp_challenges_phone_created', table_name='otp_challenges')
    op.drop_index('ix_otp_challenges_id', table_name='otp_challenges')
    op.drop_table('otp_challenges')


def downgrade():
    # The columns of 0017 plus `purpose` from 0018. The codes themselves were
    # short-lived and are not restored.
    op.create_table(
        'otp_challenges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_e164', sa.String(length=16), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('purpose', sa.String(length=16), nullable=False, server_default='sign_in'),
    )
    op.create_index('ix_otp_challenges_id', 'otp_challenges', ['id'])
    op.create_index('ix_otp_challenges_phone_created', 'otp_challenges', ['phone_e164', 'created_at'])
