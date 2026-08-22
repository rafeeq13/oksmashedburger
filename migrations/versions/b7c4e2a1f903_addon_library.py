"""addon library + product addon flags

Revision ID: b7c4e2a1f903
Revises: 3d88a1a1a423
Create Date: 2026-08-22 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c4e2a1f903'
down_revision = '3d88a1a1a423'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'addon_library',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('price', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    with op.batch_alter_table('product_addons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('library_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('is_required', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('sort_order', sa.Integer(), server_default='0', nullable=True))
        batch_op.create_foreign_key('fk_product_addons_library_id', 'addon_library', ['library_id'], ['id'])


def downgrade():
    with op.batch_alter_table('product_addons', schema=None) as batch_op:
        batch_op.drop_constraint('fk_product_addons_library_id', type_='foreignkey')
        batch_op.drop_column('sort_order')
        batch_op.drop_column('is_required')
        batch_op.drop_column('library_id')
    op.drop_table('addon_library')
