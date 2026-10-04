"""Enrollment roles: cashiers, field agent attribution, approval checks

Revision ID: 0022_enrollment_roles
Revises: 0021_usage_events
Create Date: 2026-10-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0022_enrollment_roles'
down_revision = '0021_usage_events'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'venue_staff',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('user_key', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=True),
        sa.Column('role', sa.String(length=16), nullable=False, server_default='cashier'),
        sa.Column('added_by', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('removed_by', sa.String(length=128), nullable=True),
        sa.Column('removed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_venue_staff_id', 'venue_staff', ['id'])
    op.create_index('ix_venue_staff_venue_id', 'venue_staff', ['venue_id'])
    op.create_index('ix_venue_staff_user_key', 'venue_staff', ['user_key'])

    with op.batch_alter_table('venues') as batch:
        batch.add_column(sa.Column('enrolled_by', sa.String(length=128), nullable=True))
        batch.create_index('ix_venues_enrolled_by', ['enrolled_by'])
    with op.batch_alter_table('partner_requests') as batch:
        batch.add_column(sa.Column('review_checks', sa.String(length=96), nullable=True))


def downgrade():
    with op.batch_alter_table('partner_requests') as batch:
        batch.drop_column('review_checks')
    with op.batch_alter_table('venues') as batch:
        batch.drop_index('ix_venues_enrolled_by')
        batch.drop_column('enrolled_by')
    op.drop_index('ix_venue_staff_user_key', table_name='venue_staff')
    op.drop_index('ix_venue_staff_venue_id', table_name='venue_staff')
    op.drop_index('ix_venue_staff_id', table_name='venue_staff')
    op.drop_table('venue_staff')
