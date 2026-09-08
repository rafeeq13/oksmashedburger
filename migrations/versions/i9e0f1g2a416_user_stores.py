"""user_stores many-to-many

Revision ID: i9e0f1g2a416
Revises: h9d0e1f2a315
Create Date: 2026-09-06 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "i9e0f1g2a416"
down_revision = "h9d0e1f2a315"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_stores",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "store_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO user_stores (user_id, store_id) "
            "SELECT id, store_id FROM users WHERE store_id IS NOT NULL"
        )
    )


def downgrade():
    op.drop_table("user_stores")
