"""Cart: view, add, update quantity, remove, promo/points/gift-card."""
from flask import Blueprint, render_template, request, redirect, abort, session, flash

from app import cart as cartlib
from app.helpers import get_current_store
from app.models.menu import Product, ProductVariant

bp = Blueprint("cart", __name__)


@bp.get("/cart")
def view():
    store = get_current_store()
    summary = cartlib.summary(store)
    # Real "you might also like" suggestions: available items not already in the cart,
    # favouring sweets/sides — they open the same quick-add modal as the menu.
    in_cart = {ln.get("product_id") for ln in summary["lines"]}
    suggestions = []
    if store:
        items = [it for grp in store.effective_menu() for it in grp["items"]
                 if it["available"] and it["product"].id not in in_cart]
        items.sort(key=lambda it: 0 if it["product"].category.slug in ("shakes", "sides", "vegan") else 1)
        suggestions = items[:3]
    return render_template("cart/cart.html", store=store, summary=summary, suggestions=suggestions)


@bp.post("/cart/add")
def add():
    slug = request.form.get("product_slug")
    product = Product.query.filter_by(slug=slug, is_active=True).first() if slug else None
    if not product:
        pid = request.form.get("product_id", type=int)
        product = Product.query.get(pid) if pid else None
    if not product:
        abort(404)

    qty = request.form.get("qty", type=int) or 1
    variant = None
    vid = request.form.get("variant_id", type=int)
    if vid:
        v = ProductVariant.query.get(vid)
        if v and v.product_id == product.id:
            variant = v
    addon_ids = request.form.getlist("addon_ids", type=int)
    notes = request.form.get("notes", "").strip()

    cartlib.add_item(product, qty, variant, addon_ids, notes)

    if request.form.get("buy_now"):
        return redirect("/checkout")
    return redirect(request.form.get("next") or "/cart")


@bp.post("/cart/update")
def update():
    cartlib.update_qty(request.form.get("index", type=int), request.form.get("qty", type=int))
    return redirect("/cart")


@bp.post("/cart/remove")
def remove():
    cartlib.remove_item(request.form.get("index", type=int))
    return redirect("/cart")


@bp.post("/cart/promo")
def promo():
    code = request.form.get("promo", "").strip().upper()
    nxt = request.form.get("next", "/cart")
    if code:
        session["promo"] = code
        s = cartlib.summary(get_current_store())
        # Don't block on the "add $X more" minimum while the cart is still empty
        # (e.g. starting an order from a deal) — it applies once the cart qualifies.
        if s["promo"]["error"] and s["count"] > 0:
            flash(s["promo"]["error"], "error")
        elif not s["promo"]["error"]:
            flash("Deal applied! It's ready at checkout.", "success")
        else:
            flash("Deal saved, it will apply once your order qualifies.", "success")
    return redirect(nxt)


@bp.post("/cart/promo/remove")
def promo_remove():
    session.pop("promo", None)
    return redirect("/cart")


@bp.post("/cart/points")
def points():
    session["redeem_points"] = not session.get("redeem_points")
    return redirect("/cart")


@bp.post("/cart/giftcard")
def giftcard():
    code = request.form.get("giftcard", "").strip().upper()
    if code:
        session["giftcard"] = code
        s = cartlib.summary(get_current_store())
        if s["giftcard"]["error"]:
            flash(s["giftcard"]["error"], "error")
        else:
            flash(f"Gift card applied — ${s['giftcard']['applied']:.2f} credited.", "success")
    return redirect("/cart")


@bp.post("/cart/giftcard/remove")
def giftcard_remove():
    session.pop("giftcard", None)
    return redirect("/cart")
