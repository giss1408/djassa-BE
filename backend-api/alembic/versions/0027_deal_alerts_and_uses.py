"""Deal alerts and uses: push alert status on deals, offer use at the counter

Revision ID: 0027_deal_alerts_and_uses
Revises: 0026_account_deletion
Create Date: 2026-10-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0027_deal_alerts_and_uses'
down_revision = '0026_account_deletion'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('deals') as batch:
        batch.add_column(sa.Column('notified_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('notify_status', sa.String(length=16), nullable=True))

    op.create_table(
        'deal_uses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=False),
        sa.Column('venue_id', sa.Integer(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('new_customer', sa.Boolean(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=160), nullable=False),
        sa.Column('recorded_by', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_deal_uses_id', 'deal_uses', ['id'])
    op.create_index('ix_deal_uses_deal_id', 'deal_uses', ['deal_id'])
    op.create_index('ix_deal_uses_venue_id', 'deal_uses', ['venue_id'])
    op.create_index('ix_deal_uses_idempotency_key', 'deal_uses', ['idempotency_key'], unique=True)
    op.create_index('ix_deal_uses_venue_created_at', 'deal_uses', ['venue_id', 'created_at'])


def downgrade():
    op.drop_index('ix_deal_uses_venue_created_at', table_name='deal_uses')
    op.drop_index('ix_deal_uses_idempotency_key', table_name='deal_uses')
    op.drop_index('ix_deal_uses_venue_id', table_name='deal_uses')
    op.drop_index('ix_deal_uses_deal_id', table_name='deal_uses')
    op.drop_index('ix_deal_uses_id', table_name='deal_uses')
    op.drop_table('deal_uses')
    with op.batch_alter_table('deals') as batch:
        batch.drop_column('notify_status')
        batch.drop_column('notified_at')
