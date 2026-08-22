"""backfill addon library from existing product add-ons

Revision ID: c8d5f3b2a104
Revises: b7c4e2a1f903
Create Date: 2026-08-22 21:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c8d5f3b2a104'
down_revision = 'b7c4e2a1f903'
branch_labels = None
depends_on = None


def upgrade():
    """Keep every existing product_addons row intact. Seed the shared library
    from names already in use and link rows only when the price still matches."""
    conn = op.get_bind()
    pa = sa.table(
        'product_addons',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('price', sa.Numeric),
        sa.column('library_id', sa.Integer),
    )
    al = sa.table(
        'addon_library',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('price', sa.Numeric),
        sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )

    rows = conn.execute(sa.select(pa.c.id, pa.c.name, pa.c.price, pa.c.library_id)).fetchall()
    if not rows:
        return

    lib_by_name = {}
    for lid, lname, lprice in conn.execute(sa.select(al.c.id, al.c.name, al.c.price)).fetchall():
        lib_by_name[(lname or '').strip().lower()] = (lid, lprice)

    for aid, name, price, lib_id in rows:
        if lib_id:
            continue
        key = (name or '').strip().lower()
        if not key:
            continue
        if key not in lib_by_name:
            conn.execute(al.insert().values(
                name=(name or '').strip(), price=price, sort_order=0, is_active=True,
            ))
            new_id = conn.execute(sa.text(
                "SELECT id FROM addon_library WHERE name = :name ORDER BY id DESC LIMIT 1"
            ), {"name": (name or '').strip()}).scalar()
            lib_by_name[key] = (new_id, price)
        lid, lprice = lib_by_name[key]
        # Link only when prices match — otherwise keep as a legacy item-only add-on.
        try:
            same_price = price is not None and lprice is not None and round(float(price), 2) == round(float(lprice), 2)
        except (TypeError, ValueError):
            same_price = price == lprice
        if same_price:
            conn.execute(pa.update().where(pa.c.id == aid).values(library_id=lid))


def downgrade():
    # Unlink imported rows; library table is dropped by the parent migration downgrade.
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE product_addons SET library_id = NULL WHERE library_id IS NOT NULL"))
