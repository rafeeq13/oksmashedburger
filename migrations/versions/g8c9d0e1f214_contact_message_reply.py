"""contact message reply fields

Revision ID: g8c9d0e1f214
Revises: f6a7b8c9d012
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa


revision = "g8c9d0e1f214"
down_revision = "f6a7b8c9d012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contact_messages", sa.Column("reply_text", sa.Text(), nullable=True))
    op.add_column("contact_messages", sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("contact_messages", "replied_at")
    op.drop_column("contact_messages", "reply_text")
