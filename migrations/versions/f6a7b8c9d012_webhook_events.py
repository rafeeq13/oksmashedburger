"""webhook events log

Revision ID: f6a7b8c9d012
Revises: e5f6a7b8c901
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d012"
down_revision = "e5f6a7b8c901"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_events_store_id", "webhook_events", ["store_id"])
    op.create_index("ix_webhook_events_provider", "webhook_events", ["provider"])
    op.create_index("ix_webhook_events_external_id", "webhook_events", ["external_id"])


def downgrade():
    op.drop_index("ix_webhook_events_external_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_provider", table_name="webhook_events")
    op.drop_index("ix_webhook_events_store_id", table_name="webhook_events")
    op.drop_table("webhook_events")
