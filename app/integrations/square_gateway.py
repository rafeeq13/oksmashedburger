"""Push each store's web orders to that store's Square location (Orders API).

Uses per-store `location_id` + `access_token` from Admin → Integrations → Square.
Sandbox hits connect.squareupsandbox.com; production hits connect.squareup.com.
"""
import json
import uuid
import urllib.error
import urllib.request

from app.integrations.config import active_integration_config, integration_enabled, integration_env, should_simulate
from app.services.order_details import format_item_options, money_cents

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
            "name": it.name[:512],
            "quantity": str(it.qty),
            "base_price_money": {"amount": money_cents(it.unit_price), "currency": currency},
        }
        note = format_item_options(it)
        if note:
            li["note"] = note[:2000]
        items.append(li)
    return items


def _build_service_charges(order):
    currency = (order.currency or "USD").upper()
    charges = []
    if float(order.tax or 0) > 0:
        charges.append({
            "name": "Sales Tax",
            "amount_money": {"amount": money_cents(order.tax), "currency": currency},
            "calculation_phase": "TOTAL_PHASE",
        })
    if order.order_type == "delivery" and float(order.delivery_fee or 0) > 0:
        charges.append({
            "name": "Delivery",
            "amount_money": {"amount": money_cents(order.delivery_fee), "currency": currency},
            "calculation_phase": "TOTAL_PHASE",
        })
    if float(order.tip or 0) > 0:
        charges.append({
            "name": "Tip",
            "amount_money": {"amount": money_cents(order.tip), "currency": currency},
            "calculation_phase": "TOTAL_PHASE",
        })
    return charges


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


def build_square_order(order, store):
    cfg = store_square_config(store)
    location_id = (cfg.get("location_id") or "").strip()
    currency = (order.currency or "USD").upper()
    body = {
        "location_id": location_id,
        "reference_id": (order.number or "")[:40],
        "line_items": _build_line_items(order),
        "metadata": {
            "order_number": order.number or "",
            "store_slug": store.slug if store else "",
            "order_type": order.order_type or "",
            "customer_name": (order.customer_name or "")[:100],
            "customer_email": (order.customer_email or "")[:100],
            "payment_method": order.payment_method or "",
        },
    }
    service_charges = _build_service_charges(order)
    if service_charges:
        body["service_charges"] = service_charges
    discounts = _build_discounts(order)
    if discounts:
        body["discounts"] = discounts
    if order.notes:
        body["note"] = ("Web order %s — %s" % (order.number, order.notes))[:500]
    else:
        body["note"] = "Web order %s" % order.number
    return body, location_id, currency


def _pay_external(store, order, square_order_id, location_id, currency, stripe_ref=None):
    """Mark Square order paid when checkout used Stripe / external card."""
    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "amount_money": {"amount": money_cents(order.total), "currency": currency},
        "source_id": "EXTERNAL",
        "location_id": location_id,
        "order_id": square_order_id,
        "external_details": {
            "type": "CARD",
            "source": "Stripe" if stripe_ref else "Online",
            "source_id": (stripe_ref or order.number or "")[:255],
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
                    "raw": {"error": "location_id is your Application ID — use the Location ID (starts with L). "
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
