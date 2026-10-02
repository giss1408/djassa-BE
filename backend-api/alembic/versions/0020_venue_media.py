"""Shop photos and videos

Revision ID: 0020_venue_media
Revises: 0019_merchant_onboarding
Create Date: 2026-10-02 00:00:00.000003
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0020_venue_media'
down_revision = '0019_merchant_onboarding'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'venue_media',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='processing'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('variants', sa.Text(), nullable=True),
        sa.Column('duration_s', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(length=255), nullable=True),
        sa.Column('uploaded_by', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_venue_media_id', 'venue_media', ['id'])
    op.create_index('ix_venue_media_venue_position', 'venue_media', ['venue_id', 'position'])


def downgrade():
    op.drop_index('ix_venue_media_venue_position', table_name='venue_media')
    op.drop_index('ix_venue_media_id', table_name='venue_media')
    op.drop_table('venue_media')
