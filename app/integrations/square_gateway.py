"""Push each store's web orders to that store's Square location (Orders API).

Uses per-store `location_id` + `access_token` from Admin → Integrations → Square.
Sandbox hits connect.squareupsandbox.com; production hits connect.squareup.com.
"""
import json
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from app.integrations.config import active_integration_config, integration_enabled, integration_env, should_simulate
from app.services.order_details import (
    square_kitchen_fulfillment_note,
    square_line_item_instruction,
    square_line_item_modifiers,
    square_line_item_name,
    square_order_header_note,
    money_cents,
)

SQUARE_VERSION = "2024-10-17"


def store_square_config(store):
    if not store or not integration_enabled(store, "square"):
        return {}
    return active_integration_config(store, "square")


def is_enabled(store):
    cfg = store_square_config(store)
    loc = (cfg.get("location_id") or "").strip()
    if loc.startswith("sandbox-sq0idb") or loc.startswith("sq0idb-"):
        return False
    return bool((cfg.get("access_token") or "").strip() and loc)


def _api_base(store):
    if integration_env(store) == "production":
        return "https://connect.squareup.com"
    return "https://connect.squareupsandbox.com"


def _request(store, method, path, body=None):
    cfg = store_square_config(store)
    token = (cfg.get("access_token") or "").strip()
    if not token:
        return {"error": "access_token missing"}
    url = _api_base(store) + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
            "Square-Version": SQUARE_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {"error": e.reason or "http_%s" % e.code}
        payload["_http_status"] = e.code
        return payload
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}


def _build_line_items(order):
    items = []
    currency = (order.currency or "USD").upper()
    for it in order.items:
        li = {
            "name": square_line_item_name(it),
            "quantity": str(it.qty),
            "base_price_money": {"amount": money_cents(it.unit_price), "currency": currency},
        }
        mods = square_line_item_modifiers(it, currency)
        if mods:
            li["modifiers"] = mods
        instruction = square_line_item_instruction(it)
        if instruction:
            li["note"] = instruction
        items.append(li)
    return _embed_cashier_charges(order, items)


def _embed_cashier_charges(order, items):
    """Roll tax, delivery, and tip into line-item prices | cashier shows items + total only."""
    extra = money_cents(order.delivery_fee) + money_cents(order.tip) + money_cents(order.tax)
    if extra <= 0 or not items:
        return items

    weighted = []
    for li in items:
        qty = max(1, int(float(li.get("quantity", "1"))))
        weighted.append([li, qty, li["base_price_money"]["amount"] * qty])

    total_w = sum(w[2] for w in weighted)
    if total_w <= 0:
        return items

    allocated = 0
    for i, (li, qty, line_cents) in enumerate(weighted):
        add = (extra - allocated) if i == len(weighted) - 1 else (line_cents * extra) // total_w
        allocated += add
        new_total = line_cents + add
        if new_total % qty != 0 and qty > 1:
            base_name = li.get("name") or "Item"
            li["name"] = ("%s x%s" % (base_name, qty))[:512]
            li["quantity"] = "1"
            li["base_price_money"]["amount"] = new_total
        else:
            li["base_price_money"]["amount"] = new_total // qty
    return items


def _build_service_charges(order):
    """No separate charge lines on cashier receipt."""
    return []


def _build_discounts(order):
    currency = (order.currency or "USD").upper()
    total_disc = float(order.discount or 0) + float(order.gift_card_applied or 0)
    if total_disc <= 0:
        return []
    name = "Discount"
    if order.coupon_code:
        name += " (%s)" % order.coupon_code
    elif float(order.gift_card_applied or 0) > 0:
        name = "Gift card"
    return [{
        "name": name[:255],
        "type": "FIXED_AMOUNT",
        "amount_money": {"amount": money_cents(total_disc), "currency": currency},
        "scope": "ORDER",
    }]


def _iso_utc(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _prep_duration(minutes):
    return "PT%dM" % max(1, int(minutes or 15))


def _build_fulfillments(order, store):
    """Pickup fulfillment so paid web orders route to Square KDS + kitchen/cashier printers."""
    prep_min = (store.avg_prep_minutes if store else None) or 15
    recipient = {
        "display_name": (order.customer_name or "Guest")[:255],
    }
    if order.customer_phone:
        recipient["phone_number"] = order.customer_phone[:17]
    if order.customer_email:
        recipient["email_address"] = order.customer_email[:254]
    # Delivery address goes in fulfillment note (kitchen) — not structured address
    # (structured address can print on the cashier receipt header/footer).

    pickup_details = {"recipient": recipient}
    kitchen_note = square_kitchen_fulfillment_note(order)
    if kitchen_note:
        pickup_details["note"] = kitchen_note

    if order.scheduled_for:
        pickup_details["schedule_type"] = "SCHEDULED"
        pickup_details["pickup_at"] = _iso_utc(order.scheduled_for)
        pickup_details["prep_time_duration"] = _prep_duration(prep_min)
    else:
        pickup_details["schedule_type"] = "ASAP"
        # Short prep so the ticket hits KDS/printers right after payment (sound alert).
        pickup_details["prep_time_duration"] = "PT1M"
        pickup_details["pickup_at"] = _iso_utc(datetime.now(timezone.utc) + timedelta(minutes=1))

    return [{
        "type": "PICKUP",
        "state": "PROPOSED",
        "uid": str(uuid.uuid4()),
        "pickup_details": pickup_details,
    }]


def build_square_order(order, store):
    cfg = store_square_config(store)
    location_id = (cfg.get("location_id") or "").strip()
    currency = (order.currency or "USD").upper()
    body = {
        "location_id": location_id,
        "reference_id": (order.number or "")[:40],
        "ticket_name": (order.number or "WEB")[:30],
        "line_items": _build_line_items(order),
        "metadata": {
            "order_number": order.number or "",
            "store_slug": store.slug if store else "",
            "order_type": order.order_type or "",
            "customer_name": (order.customer_name or "")[:100],
            "customer_email": (order.customer_email or "")[:100],
            "customer_phone": (order.customer_phone or "")[:30],
            "payment_method": order.payment_method or "",
            "source": "website",
        },
        "source": {"name": "OK Website"},
        "fulfillments": _build_fulfillments(order, store),
    }
    service_charges = _build_service_charges(order)
    if service_charges:
        body["service_charges"] = service_charges
    discounts = _build_discounts(order)
    if discounts:
        body["discounts"] = discounts
    body["note"] = square_order_header_note(order)
    return body, location_id, currency


def _pay_external(store, order, square_order_id, location_id, currency, stripe_ref=None):
    """Mark Square order paid when checkout used Stripe / external card."""
    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "amount_money": {"amount": money_cents(order.total), "currency": currency},
        "source_id": "EXTERNAL",
        "location_id": location_id,
        "order_id": square_order_id,
        "reference_id": (order.number or "")[:40],
        "note": ("Web %s" % (order.number or ""))[:500],
        "external_details": {
            "type": "CARD",
            "source": "Stripe" if stripe_ref else "Website",
            "source_id": (order.number or stripe_ref or "")[:255],
        },
    }
    return _request(store, "POST", "/v2/payments", payload)


def push_order(store, order, stripe_ref=None):
    """Create (and optionally pay) a Square order for this web order.

    Returns {status, reference, raw}.
    """
    cfg = store_square_config(store)
    if should_simulate(store, "square", cfg):
        return {
            "status": "simulated",
            "reference": "sq_demo_%s" % (order.number or "order"),
            "raw": {
                "demo": True,
                "location_id": cfg.get("location_id"),
                "order_number": order.number,
                "total": float(order.total or 0),
            },
        }

    if not is_enabled(store):
        loc = (cfg.get("location_id") or "").strip()
        if loc.startswith("sandbox-sq0idb") or loc.startswith("sq0idb-"):
            return {"status": "failed", "reference": None,
                    "raw": {"error": "location_id is your Application ID | use the Location ID (starts with L). "
                                     "See Admin → Square hint or run tools/list_square_locations.py."}}
        return {"status": "skipped", "reference": None,
                "raw": {"error": "Square location_id + access_token required"}}

    sq_order, location_id, currency = build_square_order(order, store)
    created = _request(store, "POST", "/v2/orders", {
        "idempotency_key": str(uuid.uuid4()),
        "order": sq_order,
    })
    if created.get("errors"):
        return {"status": "failed", "reference": None, "raw": created}

    square_order = created.get("order") or {}
    square_id = square_order.get("id")
    if not square_id:
        return {"status": "failed", "reference": None, "raw": created}

    pay_raw = None
    if order.payment_status == "paid":
        pay_raw = _pay_external(store, order, square_id, location_id, currency, stripe_ref=stripe_ref)
        if pay_raw.get("errors"):
            return {"status": "partial", "reference": square_id,
                    "raw": {"order": created, "payment": pay_raw}}

    return {
        "status": "synced",
        "reference": square_id,
        "raw": {"order": created, "payment": pay_raw},
    }


def cancel_order(store, square_order_id):
    """Cancel an existing Square order (e.g. when admin cancels a web order)."""
    cfg = store_square_config(store)
    if should_simulate(store, "square", cfg):
        return {
            "status": "simulated",
            "reference": square_order_id,
            "raw": {"demo": True, "order_id": square_order_id},
        }

    if not is_enabled(store) or not square_order_id:
        return {"status": "skipped", "reference": square_order_id,
                "raw": {"error": "Square not configured or no square order id"}}

    current = _request(store, "GET", "/v2/orders/%s" % square_order_id)
    if current.get("errors"):
        return {"status": "failed", "reference": square_order_id, "raw": current}

    sq_order = current.get("order") or {}
    state = (sq_order.get("state") or "").upper()
    if state in ("CANCELED", "CANCELLED", "COMPLETED"):
        return {"status": "skipped", "reference": square_order_id,
                "raw": {"reason": "already_%s" % state.lower()}}

    version = sq_order.get("version")
    if version is None:
        return {"status": "failed", "reference": square_order_id,
                "raw": {"error": "missing order version", "order": sq_order}}

    updated = _request(store, "PUT", "/v2/orders/%s" % square_order_id, {
        "idempotency_key": str(uuid.uuid4()),
        "order": {"state": "CANCELED", "version": version},
    })
    if updated.get("errors"):
        return {"status": "failed", "reference": square_order_id, "raw": updated}

    return {
        "status": "cancelled",
        "reference": square_order_id,
        "raw": updated,
    }
