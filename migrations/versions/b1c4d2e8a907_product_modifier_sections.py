"""product variant section heading and order

Revision ID: b1c4d2e8a907
Revises: f3a8b2c1d904
Create Date: 2026-08-25 01:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c4d2e8a907'
down_revision = 'f3a8b2c1d904'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('variants_section_label', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('variants_section_order', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('variants_section_order')
        batch_op.drop_column('variants_section_label')
