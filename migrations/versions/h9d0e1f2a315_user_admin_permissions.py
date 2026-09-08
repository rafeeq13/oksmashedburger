"""user admin_permissions

Revision ID: h9d0e1f2a315
Revises: g8c9d0e1f214
Create Date: 2026-09-05 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "h9d0e1f2a315"
down_revision = "g8c9d0e1f214"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("admin_permissions", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("admin_permissions")
