"""addon modifier section headings table

Revision ID: c3e4f5a6b709
Revises: b1c4d2e8a907
Create Date: 2026-08-25 22:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3e4f5a6b709'
down_revision = 'b1c4d2e8a907'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'product_modifier_sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=80), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('product_addons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('section_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_product_addons_section_id', 'product_modifier_sections', ['section_id'], ['id'],
        )

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT DISTINCT product_id, group_label FROM product_addons "
        "WHERE group_label IS NOT NULL AND TRIM(group_label) != ''"
    )).fetchall()
    for product_id, label in rows:
        clean = label.strip()
        conn.execute(
            sa.text(
                "INSERT INTO product_modifier_sections (product_id, label, sort_order) "
                "VALUES (:pid, :label, 0)"
            ),
            {"pid": product_id, "label": clean},
        )
        sid = conn.execute(
            sa.text(
                "SELECT id FROM product_modifier_sections "
                "WHERE product_id = :pid AND label = :label ORDER BY id DESC LIMIT 1"
            ),
            {"pid": product_id, "label": clean},
        ).scalar()
        conn.execute(
            sa.text(
                "UPDATE product_addons SET section_id = :sid "
                "WHERE product_id = :pid AND group_label = :label"
            ),
            {"sid": sid, "pid": product_id, "label": label},
        )


def downgrade():
    with op.batch_alter_table('product_addons', schema=None) as batch_op:
        batch_op.drop_constraint('fk_product_addons_section_id', type_='foreignkey')
        batch_op.drop_column('section_id')
    op.drop_table('product_modifier_sections')
