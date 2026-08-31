"""store integration_env sandbox/production

Revision ID: d4e5f6a7b810
Revises: c3e4f5a6b709
Create Date: 2026-08-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b810'
down_revision = 'c3e4f5a6b709'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stores', sa.Column('integration_env', sa.String(length=20),
                                     server_default='sandbox', nullable=False))


def downgrade():
    op.drop_column('stores', 'integration_env')
