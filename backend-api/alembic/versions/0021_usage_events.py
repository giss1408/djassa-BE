"""App usage events for the pilot (installs, screens, content seen)

Revision ID: 0021_usage_events
Revises: 0020_venue_media
"""
from alembic import op
import sqlalchemy as sa

revision = '0021_usage_events'
down_revision = '0020_venue_media'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'usage_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('app', sa.String(length=16), nullable=False),
        sa.Column('install_id', sa.String(length=40), nullable=False),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column('props', sa.Text(), nullable=True),
        sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('app_version', sa.String(length=32), nullable=False),
        sa.Column('platform', sa.String(length=16), nullable=False),
        sa.Column('os_version', sa.String(length=64), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_usage_events_id', 'usage_events', ['id'])
    op.create_index('ix_usage_events_app_occurred', 'usage_events', ['app', 'occurred_at'])
    op.create_index('ix_usage_events_install', 'usage_events', ['install_id'])
    op.create_index('ix_usage_events_venue_id', 'usage_events', ['venue_id'])


def downgrade() -> None:
    op.drop_table('usage_events')
