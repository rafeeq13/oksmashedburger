"""Shared order breakdown | same numbers everywhere (Stripe, Square, emails, Uber)."""
from decimal import Decimal


def _money(v):
    return "$%.2f" % float(v or 0)


def addon_qty(addon):
    return max(1, int((addon or {}).get("qty", 1)))


def addon_total(addon):
    a = addon or {}
    return round(float(a.get("price", 0)) * addon_qty(a), 2)


def item_option_lines(item, include_prices=False):
    """Structured modifier lines for emails and admin (not Square tickets)."""
    opts = item.options if hasattr(item, "options") else (item or {})
    if not isinstance(opts, dict):
        opts = {}
    lines = []
    if opts.get("variant"):
        v = opts["variant"]
        vd = opts.get("variant_delta")
        if include_prices and vd not in (None, "", 0, 0.0):
            lines.append("%s (%s%s)" % (v, "+" if float(vd) >= 0 else "−", _money(abs(float(vd)))))
        else:
            lines.append(v)
    for a in opts.get("addons") or []:
        qty = addon_qty(a)
        label = a.get("name", "Add-on")
        if qty > 1:
            prefix = "+ %s x%d" % (label, qty)
        else:
            prefix = "+ %s" % label
        if include_prices:
            total = addon_total(a)
            if total:
                prefix += " (+%s)" % _money(total)
        lines.append(prefix)
    if opts.get("notes"):
        lines.append('"%s"' % opts["notes"])
    return lines


def square_line_item_name(item):
    """Main line on Square kitchen/cashier tickets (size in the title, not as a modifier)."""
    opts = item.options if hasattr(item, "options") else (item or {})
    if not isinstance(opts, dict):
        opts = {}
    name = item.name if hasattr(item, "name") else str(item)
    variant = (opts.get("variant") or "").strip()
    if variant:
        name = "%s - %s" % (name, variant)
    return name[:512]


def square_modifier_lines(item):
    """Modifiers only — printed under the item name on Square tickets."""
    opts = item.options if hasattr(item, "options") else (item or {})
    if not isinstance(opts, dict):
        opts = {}
    lines = []
    for a in opts.get("addons") or []:
        qty = addon_qty(a)
        label = a.get("name", "Add-on")
        if qty > 1:
            lines.append("+ %s x%d" % (label, qty))
        else:
            lines.append("+ %s" % label)
    note = (opts.get("notes") or "").strip()
    if note:
        lines.append("- %s" % note)
    return lines


def square_line_item_modifiers(item, currency="USD"):
    """Structured add-ons for Square tickets (one modifier per line, no prices on kitchen)."""
    opts = item.options if hasattr(item, "options") else (item or {})
    if not isinstance(opts, dict):
        opts = {}
    mods = []
    for a in opts.get("addons") or []:
        qty = addon_qty(a)
        label = a.get("name", "Add-on")
        if qty > 1:
            name = "+ %s x%d" % (label, qty)
        else:
            name = "+ %s" % label
        mods.append({
            "name": name[:255],
            "quantity": "1",
            "base_price_money": {"amount": 0, "currency": (currency or "USD").upper()},
        })
    return mods


def square_line_item_instruction(item):
    """Per-item special instructions (not add-ons) on a Square line item."""
    opts = item.options if hasattr(item, "options") else (item or {})
    if not isinstance(opts, dict):
        return ""
    return (opts.get("notes") or "").strip()[:2000]


def square_item_note(item):
    """Legacy note field — prefer modifiers + square_line_item_instruction."""
    return square_line_item_instruction(item)


def square_order_header_note(order, include_delivery_address=False):
    """Order note on Square tickets — no delivery address (kitchen gets that via fulfillment note)."""
    parts = ["WEB ORDER %s" % (order.number or "—")]
    otype = (order.order_type or "").strip().upper()
    if otype:
        parts.append(otype.replace("_", " "))
    if order.customer_name:
        parts.append(order.customer_name)
    if order.customer_phone:
        parts.append(order.customer_phone)
    if include_delivery_address and order.order_type == "delivery" and order.address:
        parts.append((order.address or "")[:160])
    note_text = (order.notes or "").strip()
    if note_text:
        parts.extend(["", ""])
        parts.append('Customer Note : "%s"' % note_text[:240])
    return "\n".join(parts)[:500]


def square_kitchen_fulfillment_note(order):
    """Delivery address on kitchen ticket only (Square fulfillment note)."""
    if (order.order_type or "").lower() != "delivery":
        return ""
    bits = ["DELIVERY"]
    addr = (order.address or "").strip()
    if not addr and getattr(order, "address_line1", None):
        parts = [order.address_line1]
        if getattr(order, "address_line2", None):
            parts.append(order.address_line2)
        city = getattr(order, "address_city", None)
        state = getattr(order, "address_state", None)
        zipc = getattr(order, "address_zip", None)
        if city or state or zipc:
            parts.append(", ".join(p for p in [city, state, zipc] if p))
        addr = ", ".join(p for p in parts if p)
    if addr:
        bits.append(addr[:220])
    return "\n".join(bits)[:500]


def format_item_options(item):
    lines = item_option_lines(item, include_prices=True)
    return " · ".join(lines)


def format_item_options_multiline(item, include_prices=False):
    return "\n".join(item_option_lines(item, include_prices=include_prices))


def order_email_rows(order):
    """Detail rows for order emails and admin previews."""
    store = order.store
    rows = [
        ("Order number", order.number),
        ("Store", store.name if store else "n/a"),
        ("Type", (order.order_type or "delivery").title()),
    ]
    if order.customer_name:
        rows.append(("Customer", order.customer_name))
    if order.address:
        rows.append(("Address", order.address))
    for it in order.items:
        detail_lines = item_option_lines(it, include_prices=True)
        label = "%d× %s" % (it.qty, it.name)
        value = _money(it.line_total)
        if detail_lines:
            value = "%s\n%s" % (value, "\n".join(detail_lines))
        rows.append((label, value))
    rows.extend(order_charge_rows(order))
    return rows


def order_email_html(order):
    """Premium order breakdown block for HTML emails (no receipt link, PDF attached)."""
    store_name = order.store.name if order.store else "n/a"
    otype = (order.order_type or "delivery").title()
    parts = [
        '<div style="background:#faf9f7;border-radius:16px;padding:24px 22px;margin:0 0 24px;'
        'border:1px solid #ebe8e0">',
        '<div style="margin-bottom:18px">',
        '<span style="display:inline-block;background:#141414;color:#FFC72C;padding:8px 16px;'
        'border-radius:999px;font-size:12px;font-weight:800;letter-spacing:.1em">',
        _esc(order.number or ""), '</span>',
        '</div>',
        '<p style="margin:0 0 6px;font-size:13px;color:#777;line-height:1.5">',
        '<strong style="color:#141414">%s</strong> · %s' % (_esc(store_name), _esc(otype)),
        '</p>',
    ]
    if order.customer_name:
        parts.append('<p style="margin:0 0 6px;font-size:13px;color:#777">%s</p>' % _esc(order.customer_name))
    if order.address:
        parts.append('<p style="margin:0;font-size:13px;color:#777">%s</p>' % _esc(order.address))
    if order.notes:
        parts.append(
            '<p style="margin:10px 0 0;font-size:13px;color:#141414;line-height:1.5">'
            '<strong>Instructions:</strong> %s</p>' % _esc(order.notes)
        )

    parts.append('<div style="margin-top:22px;padding-top:18px;border-top:1px solid #e3e0d8">')
    for it in order.items:
        detail_lines = item_option_lines(it, include_prices=True)
        item_label = _esc("%d× %s" % (it.qty, it.name))
        line_price = _esc(_money(it.line_total))
        parts.append(
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="margin-bottom:14px"><tr>'
            '<td style="vertical-align:top;padding:0">'
            '<div style="font-size:15px;font-weight:700;color:#141414;line-height:1.35">'
            + item_label + '</div>'
        )
        for line in detail_lines:
            parts.append(
                '<div style="font-size:12px;color:#c0392b;margin-top:3px;line-height:1.45;padding-left:8px">'
                + _esc(line) + '</div>'
            )
        parts.append(
            '</td><td align="right" style="vertical-align:top;padding:0 0 0 12px;'
            'font-size:15px;font-weight:700;color:#141414;white-space:nowrap">'
            + line_price + '</td></tr></table>'
        )
    parts.append('</div>')

    charge_rows = order_charge_rows(order)
    parts.append(
        '<div style="margin-top:8px;padding:16px 14px 14px;border-top:2px solid #141414;'
        'background:#f5f4f1;border-radius:0 0 12px 12px">'
    )
    for label, value in charge_rows:
        if label == "Total":
            continue
        is_discount = str(value).startswith("−")
        style_val = "font-size:14px;font-weight:700;color:#2a9d4b" if is_discount else "font-size:14px;font-weight:700;color:#141414"
        parts.append(
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="margin-bottom:6px"><tr>'
            '<td style="font-size:14px;font-weight:500;color:#666">' + _esc(label) + '</td>'
            '<td align="right" style="' + style_val + '">' + _esc(value) + '</td>'
            '</tr></table>'
        )
    total_val = next((v for l, v in charge_rows if l == "Total"), _money(order.total))
    parts.append(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin-top:10px;background:#141414;border-radius:10px">'
        '<tr><td style="padding:14px 16px;font-size:15px;font-weight:800;color:#ffffff">Total</td>'
        '<td align="right" style="padding:14px 16px;font-size:20px;font-weight:800;color:#FFC72C">'
        + _esc(total_val) + '</td></tr></table>'
    )
    parts.append('</div></div>')
    return "".join(parts)


def _esc(text):
    from markupsafe import escape
    return str(escape(text or "")).replace("\n", "<br>")


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
    """Stripe / provider metadata, charges, customer, delivery, items."""
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
