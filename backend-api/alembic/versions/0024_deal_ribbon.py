"""Deal ribbon: the corner banner on a deal's image (bon plan, flash, promo)

Revision ID: 0024_deal_ribbon
Revises: 0023_loyalty_consents
Create Date: 2026-10-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0024_deal_ribbon'
down_revision = '0023_loyalty_consents'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('deals') as batch:
        batch.add_column(sa.Column('ribbon', sa.String(length=16), nullable=False, server_default='bon_plan'))


def downgrade():
    with op.batch_alter_table('deals') as batch:
        batch.drop_column('ribbon')
