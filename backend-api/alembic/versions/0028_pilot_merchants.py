"""Pilot merchants: baseline, self-declared gender and day-45 commitment

Revision ID: 0028_pilot_merchants
Revises: 0027_deal_alerts_and_uses
Create Date: 2026-10-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0028_pilot_merchants'
down_revision = '0027_deal_alerts_and_uses'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pilot_merchants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('baseline_recorded_at', sa.DateTime(), nullable=True),
        sa.Column('baseline_tickets_per_day', sa.Integer(), nullable=True),
        sa.Column('baseline_average_basket', sa.Integer(), nullable=True),
        sa.Column('baseline_mobile_money_pct', sa.Integer(), nullable=True),
        sa.Column('baseline_repeat_pct', sa.Integer(), nullable=True),
        sa.Column('owner_gender', sa.String(length=16), nullable=True),
        sa.Column('commitment', sa.String(length=16), nullable=True),
        sa.Column('commitment_plan', sa.String(length=16), nullable=True),
        sa.Column('commitment_price', sa.Integer(), nullable=True),
        sa.Column('commitment_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.String(length=128), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_pilot_merchants_id', 'pilot_merchants', ['id'])
    op.create_index('ix_pilot_merchants_venue_id', 'pilot_merchants', ['venue_id'], unique=True)


def downgrade():
    op.drop_index('ix_pilot_merchants_venue_id', table_name='pilot_merchants')
    op.drop_index('ix_pilot_merchants_id', table_name='pilot_merchants')
    op.drop_table('pilot_merchants')
