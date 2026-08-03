"""Session-based cart (SRS §4.4). Items snapshot name/price so the cart is
stable even if the catalog changes. Totals are always computed server-side
using the CURRENT store's tax rate and delivery fee."""
from flask import session

from .models.menu import Product, ProductVariant, ProductAddon


def get_cart():
    return session.get("cart", [])


def _save(cart):
    session["cart"] = cart
    session.modified = True


def add_item(product, qty=1, variant=None, addon_ids=None, notes=""):
    unit = float(product.base_price)
    options = {}
    if variant:
        unit += float(variant.price_delta)
        options["variant"] = variant.name
        options["variant_delta"] = float(variant.price_delta)
    addons = []
    for aid in (addon_ids or []):
        addon = ProductAddon.query.get(aid)
        if addon and addon.product_id == product.id:
            unit += float(addon.price)
            addons.append({"name": addon.name, "price": float(addon.price)})
    if addons:
        options["addons"] = addons
    if notes:
        options["notes"] = notes

    cart = get_cart()
    cart.append({
        "product_id": product.id,
        "slug": product.slug,
        "name": product.name,
        "image": product.image_url,
        "unit_price": round(unit, 2),
        "qty": max(1, int(qty)),
        "options": options,
    })
    _save(cart)


def update_qty(index, qty):
    cart = get_cart()
    if index is None or not (0 <= index < len(cart)):
        return
    if qty is None or qty <= 0:
        cart.pop(index)
    else:
        cart[index]["qty"] = int(qty)
    _save(cart)


def remove_item(index):
    cart = get_cart()
    if index is not None and 0 <= index < len(cart):
        cart.pop(index)
        _save(cart)


def clear():
    for k in ("cart", "promo", "redeem_points", "giftcard"):
        session.pop(k, None)


def summary(store, tip=0.0, order_type="delivery"):
    """Full pricing incl. promo code, loyalty-points redemption and gift card,
    all resolved from the session + current user (SRS §4.9)."""
    from flask import session
    from app.auth import current_user
    from app.models.promo import Coupon, GiftCard

    cart = get_cart()
    lines, subtotal = [], 0.0
    for i, it in enumerate(cart):
        line_total = round(it["unit_price"] * it["qty"], 2)
        subtotal += line_total
        lines.append({"index": i, "line_total": line_total, **it})
    subtotal = round(subtotal, 2)

    tax_rate = float(store.tax_rate) if store else 0.08
    base_delivery = 0.0
    if order_type == "delivery" and store:
        # Use the closest active delivery zone (smallest radius) as this store's fee.
        active = [z for z in store.delivery_zones if z.is_active]
        pool = active or list(store.delivery_zones)
        if pool:
            closest = min(pool, key=lambda z: (z.radius_miles or 0))
            base_delivery = float(closest.delivery_fee)
        else:
            base_delivery = 2.99

    # ── Promo code ────────────────────────────────────────────
    promo = {"code": None, "discount": 0.0, "delivery_discount": 0.0, "error": None, "desc": None}
    code = session.get("promo")
    if code:
        c = Coupon.query.filter_by(code=code.upper()).first()
        if not c:
            promo["code"], promo["error"] = code, "Invalid promo code."
        else:
            ok, err = c.validate(subtotal)
            promo["code"], promo["desc"] = c.code, c.description
            if ok:
                comp = c.compute(subtotal, base_delivery)
                promo["discount"], promo["delivery_discount"] = comp["order_discount"], comp["delivery_discount"]
            else:
                promo["error"] = err

    order_discount = promo["discount"]
    delivery_fee = max(0.0, round(base_delivery - promo["delivery_discount"], 2))

    # ── Loyalty points redemption (100 pts = $1) ──────────────
    user = current_user()
    points = {"available": user.loyalty_points if user else 0, "redeemed": False, "dollars": 0.0, "points_used": 0}
    if session.get("redeem_points") and user and user.loyalty_points > 0:
        cap = max(0.0, round(subtotal - order_discount, 2))
        dollars = round(min(user.loyalty_points * 0.01, cap), 2)
        if dollars > 0:
            points.update(redeemed=True, dollars=dollars, points_used=int(round(dollars * 100)))
            order_discount += dollars

    order_discount = round(order_discount, 2)
    taxed_base = max(0.0, round(subtotal - order_discount, 2))
    tax = round(taxed_base * tax_rate, 2)
    tip = round(float(tip or 0), 2)
    total_before_gc = round(taxed_base + tax + delivery_fee + tip, 2)

    # ── Gift card (applied as credit against the total) ───────
    giftcard = {"code": None, "applied": 0.0, "balance": 0.0, "error": None}
    gc_code = session.get("giftcard")
    if gc_code:
        gc = GiftCard.query.filter_by(code=gc_code.upper(), active=True).first()
        if gc and float(gc.balance) > 0:
            giftcard.update(code=gc.code, applied=round(min(float(gc.balance), total_before_gc), 2), balance=float(gc.balance))
        elif gc:
            giftcard.update(code=gc_code, error="Gift card has no balance.")
        else:
            giftcard.update(code=gc_code, error="Invalid gift card.")

    total = round(total_before_gc - giftcard["applied"], 2)
    return {
        "lines": lines, "count": sum(l["qty"] for l in lines),
        "subtotal": subtotal, "tax": tax, "tax_rate": tax_rate,
        "delivery_fee": delivery_fee, "base_delivery": round(base_delivery, 2),
        "tip": tip, "order_discount": order_discount, "total": total,
        "promo": promo, "points": points, "giftcard": giftcard,
    }
