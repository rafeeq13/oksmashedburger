"""Shared order breakdown — same numbers everywhere (Stripe, Square, emails, Uber)."""
from decimal import Decimal


def _money(v):
    return "$%.2f" % float(v or 0)


def addon_qty(addon):
    return max(1, int((addon or {}).get("qty", 1)))


def addon_total(addon):
    a = addon or {}
    return round(float(a.get("price", 0)) * addon_qty(a), 2)


def format_item_options(item):
    opts = item.options if hasattr(item, "options") else (item or {})
    if not isinstance(opts, dict):
        opts = {}
    parts = []
    if opts.get("variant"):
        v = opts["variant"]
        vd = opts.get("variant_delta")
        if vd not in (None, "", 0, 0.0):
            parts.append("%s (%s%s)" % (v, "+" if float(vd) >= 0 else "−", _money(abs(float(vd)))))
        else:
            parts.append(v)
    for a in opts.get("addons") or []:
        qty = addon_qty(a)
        label = a.get("name", "Add-on")
        total = addon_total(a)
        if qty > 1:
            parts.append("+%s ×%d (+%s)" % (label, qty, _money(total)))
        else:
            parts.append("+%s (+%s)" % (label, _money(total)))
    if opts.get("notes"):
        parts.append('"%s"' % opts["notes"])
    return " · ".join(parts)


def order_email_rows(order):
    """Detail rows for order emails and admin previews."""
    store = order.store
    rows = [
        ("Order number", order.number),
        ("Store", store.name if store else "—"),
        ("Type", (order.order_type or "delivery").title()),
    ]
    if order.customer_name:
        rows.append(("Customer", order.customer_name))
    if order.address:
        rows.append(("Address", order.address))
    for it in order.items:
        detail = format_item_options(it)
        label = "%d× %s" % (it.qty, it.name)
        value = _money(it.line_total)
        if detail:
            value = "%s — %s" % (value, detail)
        rows.append((label, value))
    from app.services.receipts import receipt_public_url
    receipt_url = receipt_public_url(order)
    if receipt_url:
        rows.append(("Receipt PDF", receipt_url))
    rows.extend(order_charge_rows(order))
    return rows


def order_charge_rows(order):
    """Subtotal → total lines only."""
    rows = [("Subtotal", _money(order.subtotal))]
    if order.discount and float(order.discount) > 0:
        lbl = "Discount"
        if order.coupon_code:
            lbl += " (%s)" % order.coupon_code
        rows.append((lbl, "−" + _money(order.discount)))
    rows.append(("Tax", _money(order.tax)))
    if order.order_type == "delivery":
        fee = float(order.delivery_fee or 0)
        rows.append(("Delivery", _money(fee) if fee > 0 else "FREE"))
    if order.tip and float(order.tip) > 0:
        rows.append(("Tip", _money(order.tip)))
    if order.gift_card_applied and float(order.gift_card_applied) > 0:
        rows.append(("Gift card", "−" + _money(order.gift_card_applied)))
    rows.append(("Total", _money(order.total)))
    return rows


def _stripe_meta_value(value, max_len=500):
    text = str(value or "").strip()
    return text[:max_len] if text else ""


def _stripe_items_metadata(order):
    """Line items for Stripe metadata (≤50 keys, ≤500 chars each)."""
    meta = {}
    lines = []
    for it in order.items:
        detail = format_item_options(it)
        line = "%d× %s @ %s" % (it.qty, it.name, _money(it.unit_price))
        if detail:
            line += " (%s)" % detail
        lines.append(line)
    meta["item_count"] = str(len(lines))
    summary = " | ".join(lines)
    if len(summary) <= 500:
        if summary:
            meta["items"] = summary
    else:
        for idx, line in enumerate(lines[:40], start=1):
            meta["item_%d" % idx] = line[:500]
    return meta


def payment_metadata(order, extra=None):
    """Stripe / provider metadata — charges, customer, delivery, items."""
    meta = {
        "order_number": order.number or "",
        "store": order.store.slug if order.store else "",
        "store_name": _stripe_meta_value(order.store.name if order.store else ""),
        "order_type": order.order_type or "",
        "customer_name": _stripe_meta_value(order.customer_name),
        "customer_email": _stripe_meta_value(order.customer_email),
        "customer_phone": _stripe_meta_value(order.customer_phone),
        "subtotal": "%.2f" % float(order.subtotal or 0),
        "tax": "%.2f" % float(order.tax or 0),
        "delivery_fee": "%.2f" % float(order.delivery_fee or 0),
        "tip": "%.2f" % float(order.tip or 0),
        "discount": "%.2f" % float(order.discount or 0),
        "gift_card": "%.2f" % float(order.gift_card_applied or 0),
        "points_redeemed": str(int(order.points_redeemed or 0)),
        "total": "%.2f" % float(order.total or 0),
    }
    if order.order_type == "delivery" and order.address:
        meta["delivery_address"] = _stripe_meta_value(order.address)
    if order.coupon_code:
        meta["coupon"] = order.coupon_code
    if order.notes:
        meta["notes"] = _stripe_meta_value(order.notes)
    meta.update(_stripe_items_metadata(order))
    if extra:
        meta.update(extra)
    return {k: str(v)[:500] for k, v in meta.items() if v is not None and str(v).strip()}


def stripe_payment_update(order):
    """Stripe PaymentIntent fields to set after checkout creates the order."""
    meta = payment_metadata(order)
    parts = ["Order %s" % (order.number or "")]
    if order.order_type == "delivery":
        parts.append("Delivery")
    elif order.order_type == "pickup":
        parts.append("Pickup")
    if order.customer_name:
        parts.append(order.customer_name)
    update = {
        "metadata": meta,
        "description": " · ".join(parts)[:1000],
    }
    email = (order.customer_email or "").strip()
    if email:
        update["receipt_email"] = email[:800]
    if order.order_type == "delivery" and order.address_line1:
        update["shipping"] = {
            "name": _stripe_meta_value(order.customer_name, 200),
            "phone": _stripe_meta_value(order.customer_phone, 50),
            "address": {
                "line1": _stripe_meta_value(order.address_line1, 200),
                "line2": _stripe_meta_value(order.address_line2, 200),
                "city": _stripe_meta_value(order.address_city, 100),
                "state": _stripe_meta_value(order.address_state, 50),
                "postal_code": _stripe_meta_value(order.address_zip, 20),
                "country": "US",
            },
        }
    return update


def uber_payload(order):
    """Delivery dispatch payload with full charge breakdown."""
    items = []
    for it in order.items:
        items.append({
            "name": it.name,
            "qty": it.qty,
            "unit_price": float(it.unit_price),
            "line_total": float(it.line_total),
            "options": it.options or {},
        })
    return {
        "order_number": order.number,
        "store": order.store.slug if order.store else "",
        "customer": {
            "name": order.customer_name,
            "phone": order.customer_phone,
            "email": order.customer_email,
        },
        "address": order.address,
        "items": items,
        "charges": {
            "subtotal": float(order.subtotal or 0),
            "tax": float(order.tax or 0),
            "delivery_fee": float(order.delivery_fee or 0),
            "tip": float(order.tip or 0),
            "discount": float(order.discount or 0),
            "gift_card": float(order.gift_card_applied or 0),
            "total": float(order.total or 0),
        },
    }


def money_cents(amount):
    return int(round(float(amount or 0) * 100))
