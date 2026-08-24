"""store map embed url

Revision ID: d9e6a4b2c105
Revises: c8d5f3b2a104
Create Date: 2026-08-23 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd9e6a4b2c105'
down_revision = 'c8d5f3b2a104'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stores', sa.Column('map_embed_url', sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column('stores', 'map_embed_url')
