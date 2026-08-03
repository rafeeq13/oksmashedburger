"""Signed-in customer area (login required): dashboard, orders, reorder,
favorites and saved addresses."""
from flask import Blueprint, render_template, redirect, flash, session, request, Response, abort

from app import cart as cartlib
from app.extensions import db
from app.auth import login_required, current_user
from app.models.user import User
from app.models.order import Order
from app.models.menu import Product, ProductVariant, ProductAddon
from app.models.favorite import Favorite
from app.models.address import UserAddress
from app.services.orders import orders_for_user, STAGE_META

bp = Blueprint("account", __name__)


def _next_reward(points):
    target = 1500 if points < 1500 else ((points // 500) + 1) * 500
    return target, max(0, target - points), min(100, round(points / target * 100)) if target else 0


# ── Dashboard ────────────────────────────────────────────────────────────
@bp.get("/account")
@login_required
def account():
    u = current_user()
    all_orders = orders_for_user(u.id)
    target, to_go, pct = _next_reward(u.loyalty_points)
    return render_template(
        "pages/account.html",
        recent_order=all_orders[0] if all_orders else None,
        order_count=len(all_orders),
        favorites_count=len(u.favorites),
        addresses=UserAddress.query.filter_by(user_id=u.id)
        .order_by(UserAddress.is_default.desc(), UserAddress.id).all(),
        reward_target=target, reward_to_go=to_go, reward_pct=pct,
    )


# ── Orders + reorder ─────────────────────────────────────────────────────
@bp.get("/orders")
@login_required
def orders():
    all_orders = orders_for_user(current_user().id)
    active = [o for o in all_orders if o.status not in ("completed", "cancelled")]
    past = [o for o in all_orders if o.status in ("completed", "cancelled")]
    return render_template("pages/orders.html", active=active, past=past, stage_meta=STAGE_META)


@bp.get("/orders/<number>/receipt.pdf")
def receipt(number):
    """PDF receipt — the order's owner, or a guest who just placed it (session)."""
    from app.services.receipts import build_receipt_pdf
    order = Order.query.filter_by(number=number).first_or_404()
    u = current_user()
    if not ((u and order.user_id == u.id) or session.get("last_order_id") == order.id):
        abort(403)
    return Response(build_receipt_pdf(order), mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=receipt-{order.number}.pdf"})


@bp.post("/orders/<number>/reorder")
@login_required
def reorder(number):
    """Re-add a past order's items to the cart at CURRENT menu prices, and switch
    the basket to that order's store so pricing/availability match (SRS FR-4.6)."""
    order = Order.query.filter_by(number=number, user_id=current_user().id).first_or_404()
    if order.store:
        session["store_slug"] = order.store.slug

    added, skipped = 0, 0
    for it in order.items:
        product = Product.query.get(it.product_id) if it.product_id else None
        if not product or not product.is_active:
            skipped += 1
            continue
        opts = it.options or {}
        variant = None
        if opts.get("variant"):
            variant = ProductVariant.query.filter_by(product_id=product.id, name=opts["variant"]).first()
        addon_ids = []
        for a in opts.get("addons", []):
            addon = ProductAddon.query.filter_by(product_id=product.id, name=a.get("name")).first()
            if addon:
                addon_ids.append(addon.id)
        cartlib.add_item(product, it.qty, variant, addon_ids, opts.get("notes", ""))
        added += 1

    if added and skipped:
        flash(f"Added {added} item(s) to your cart — {skipped} item(s) from {order.number} are no longer available.", "success")
    elif added:
        flash(f"Added your {order.number} items to the cart. Prices reflect today's menu.", "success")
    else:
        flash("Sorry — none of those items are available to reorder right now.", "error")
    return redirect("/cart")


# ── Favorites ────────────────────────────────────────────────────────────
@bp.post("/account/profile")
@login_required
def profile_update():
    u = current_user()
    email = request.form.get("email", "").strip().lower()
    if email and email != u.email:
        if "@" not in email or User.query.filter(User.email == email, User.id != u.id).first():
            flash("That email is invalid or already in use.", "error")
            return redirect("/account")
        u.email = email
    u.first_name = request.form.get("first_name", "").strip()
    u.last_name = request.form.get("last_name", "").strip()
    u.phone = request.form.get("phone", "").strip()
    db.session.commit()
    flash("Profile updated.", "success")
    return redirect("/account")


@bp.post("/account/password")
@login_required
def password_update():
    u = current_user()
    if not u.check_password(request.form.get("current", "")):
        flash("Your current password is incorrect.", "error")
    elif len(request.form.get("new", "")) < 6:
        flash("New password must be at least 6 characters.", "error")
    elif request.form.get("new") != request.form.get("confirm"):
        flash("New passwords don't match.", "error")
    else:
        u.set_password(request.form.get("new"))
        db.session.commit()
        flash("Password changed.", "success")
    return redirect("/account")


@bp.get("/favorites")
@login_required
def favorites():
    u = current_user()
    favs = (Favorite.query.filter_by(user_id=u.id)
            .order_by(Favorite.created_at.desc()).all())
    products = [f.product for f in favs if f.product and f.product.is_active]
    recent_orders = orders_for_user(u.id)[:4]
    return render_template("pages/favorites.html", products=products, recent_orders=recent_orders)


@bp.post("/favorites/toggle")
@login_required
def favorites_toggle():
    u = current_user()
    pid = request.form.get("product_id", type=int)
    product = Product.query.get(pid) if pid else None
    if product:
        fav = Favorite.query.filter_by(user_id=u.id, product_id=product.id).first()
        if fav:
            db.session.delete(fav)
            flash(f"Removed {product.name} from favorites.", "success")
        else:
            db.session.add(Favorite(user_id=u.id, product_id=product.id))
            flash(f"Saved {product.name} to favorites.", "success")
        db.session.commit()
    return redirect(request.form.get("next") or "/favorites")


# ── Saved addresses ──────────────────────────────────────────────────────
@bp.post("/account/addresses")
@login_required
def address_add():
    u = current_user()
    line1 = request.form.get("line1", "").strip()
    if not line1:
        flash("Street address is required.", "error")
        return redirect("/account")
    make_default = bool(request.form.get("is_default")) or UserAddress.query.filter_by(user_id=u.id).count() == 0
    if make_default:
        UserAddress.query.filter_by(user_id=u.id).update({"is_default": False})
    db.session.add(UserAddress(
        user_id=u.id, label=request.form.get("label", "Home").strip() or "Home",
        recipient=request.form.get("recipient", "").strip(),
        line1=line1, line2=request.form.get("line2", "").strip(),
        city=request.form.get("city", "Philadelphia").strip() or "Philadelphia",
        state=request.form.get("state", "PA").strip() or "PA",
        zip_code=request.form.get("zip_code", "").strip(),
        phone=request.form.get("phone", "").strip(), is_default=make_default))
    db.session.commit()
    flash("Address saved.", "success")
    return redirect("/account")


@bp.post("/account/addresses/<int:aid>/default")
@login_required
def address_default(aid):
    u = current_user()
    addr = UserAddress.query.filter_by(id=aid, user_id=u.id).first_or_404()
    UserAddress.query.filter_by(user_id=u.id).update({"is_default": False})
    addr.is_default = True
    db.session.commit()
    flash("Default address updated.", "success")
    return redirect("/account")


@bp.post("/account/addresses/<int:aid>/delete")
@login_required
def address_delete(aid):
    u = current_user()
    addr = UserAddress.query.filter_by(id=aid, user_id=u.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    flash("Address removed.", "success")
    return redirect("/account")
