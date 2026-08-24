"""order delivery address fields

Revision ID: e1f8c3a4b206
Revises: d9e6a4b2c105
Create Date: 2026-08-23 23:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f8c3a4b206'
down_revision = 'd9e6a4b2c105'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('address_line1', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('address_line2', sa.String(length=120), nullable=True))
    op.add_column('orders', sa.Column('address_city', sa.String(length=80), nullable=True))
    op.add_column('orders', sa.Column('address_state', sa.String(length=40), nullable=True))
    op.add_column('orders', sa.Column('address_zip', sa.String(length=12), nullable=True))
    op.add_column('orders', sa.Column('address_lat', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('address_lng', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('orders', 'address_lng')
    op.drop_column('orders', 'address_lat')
    op.drop_column('orders', 'address_zip')
    op.drop_column('orders', 'address_state')
    op.drop_column('orders', 'address_city')
    op.drop_column('orders', 'address_line2')
    op.drop_column('orders', 'address_line1')
