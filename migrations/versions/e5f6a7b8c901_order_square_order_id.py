"""order square_order_id for Square POS sync

Revision ID: e5f6a7b8c901
Revises: d4e5f6a7b810
Create Date: 2026-08-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c901'
down_revision = 'd4e5f6a7b810'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('square_order_id', sa.String(length=80), nullable=True))
    op.create_index(op.f('ix_orders_square_order_id'), 'orders', ['square_order_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_orders_square_order_id'), table_name='orders')
    op.drop_column('orders', 'square_order_id')
