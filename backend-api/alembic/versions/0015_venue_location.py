"""Record where a venue's coordinates came from, and how precise they are

The merchant app can now set the shop's position from the phone's GPS while
the merchant stands in it; the customer app uses the coordinates for its
"Itinéraire" button. The existing latitude/longitude columns are unchanged.

Revision ID: 0015_venue_location
Revises: 0014_sale_events
Create Date: 2026-09-30 00:00:00.000005
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0015_venue_location'
down_revision = '0014_sale_events'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('venues', sa.Column('location_source', sa.String(length=16), nullable=True))
    op.add_column('venues', sa.Column('location_accuracy_m', sa.Integer(), nullable=True))
    op.add_column('venues', sa.Column('location_set_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('venues', 'location_set_at')
    op.drop_column('venues', 'location_accuracy_m')
    op.drop_column('venues', 'location_source')
