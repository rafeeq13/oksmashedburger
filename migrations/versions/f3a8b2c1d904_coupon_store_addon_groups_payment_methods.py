"""coupon store, addon groups, payment methods

Revision ID: f3a8b2c1d904
Revises: a0425f18165e
Create Date: 2026-08-25 00:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3a8b2c1d904'
down_revision = 'a0425f18165e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('coupons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('store_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_coupon_store_id', 'stores', ['store_id'], ['id'])

    with op.batch_alter_table('product_addons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('group_label', sa.String(length=80), nullable=True))

    op.create_table('user_payment_methods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('brand', sa.String(length=20), nullable=True),
        sa.Column('last4', sa.String(length=4), nullable=False),
        sa.Column('exp_month', sa.String(length=2), nullable=True),
        sa.Column('exp_year', sa.String(length=4), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_payment_method_user_id'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('user_payment_methods')
    with op.batch_alter_table('product_addons', schema=None) as batch_op:
        batch_op.drop_column('group_label')
    with op.batch_alter_table('coupons', schema=None) as batch_op:
        batch_op.drop_constraint('fk_coupon_store_id', type_='foreignkey')
        batch_op.drop_column('store_id')
