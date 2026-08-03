"""Per-store menu browsing + item detail."""
from flask import Blueprint, render_template, session, abort

from app.helpers import get_current_store
from app.models.store import Store
from app.models.menu import Product

bp = Blueprint("menu", __name__)


@bp.get("/menu")
def menu():
    store = get_current_store()
    if not store:
        return render_template("menu/menu.html", store=None, menu=[])
    return render_template("menu/menu.html", store=store, menu=store.effective_menu())


@bp.get("/menu/<store_slug>")
def menu_for_store(store_slug):
    store = Store.query.filter_by(slug=store_slug, is_active=True).first()
    if not store:
        abort(404)
    session["store_slug"] = store_slug
    return render_template("menu/menu.html", store=store, menu=store.effective_menu())


def _item_context(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first()
    if not product:
        abort(404)
    store = get_current_store()
    price = float(product.base_price)
    available = True
    if store:
        mi = next((m for m in store.menu_items if m.product_id == product.id), None)
        if mi:
            price = float(mi.price_override if mi.price_override is not None else product.base_price)
            available = mi.is_available and mi.is_listed
    return {"product": product, "price": price, "available": available, "store": store}


@bp.get("/item/<slug>")
def item(slug):
    return render_template("menu/item.html", **_item_context(slug))


@bp.get("/item/<slug>/modal")
def item_modal(slug):
    """Just the add-to-cart card (with sizes/add-ons) — loaded into the
    quick-add modal on the home and menu pages."""
    return render_template("menu/_item_modal.html", **_item_context(slug))
