"""Per-store variant and add-on price overrides."""
from alembic import op
import sqlalchemy as sa


revision = "j0f1g2h3b517"
down_revision = "i9e0f1g2a416"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "store_variant_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("price_delta", sa.Numeric(8, 2), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "variant_id", name="uq_store_variant_price"),
    )
    op.create_table(
        "store_addon_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("addon_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(8, 2), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["addon_id"], ["product_addons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "addon_id", name="uq_store_addon_price"),
    )


def downgrade():
    op.drop_table("store_addon_prices")
    op.drop_table("store_variant_prices")
