"""Third-party delivery via EACH STORE's own Uber Direct account."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from app.integrations.config import active_integration_config, integration_enabled, should_simulate

API_BASE = "https://api.uber.com"
TOKEN_URL = "https://auth.uber.com/oauth/v2/token"
_TOKEN_CACHE = {}


def store_uber_config(store):
    if not store or not integration_enabled(store, "uber_direct"):
        return {}
    return active_integration_config(store, "uber_direct")


def is_enabled(store):
    cfg = store_uber_config(store)
    return bool(
        store
        and integration_enabled(store, "uber_direct")
        and (cfg.get("customer_id") or "").strip()
        and (cfg.get("client_id") or "").strip()
        and (cfg.get("client_secret") or "").strip()
    )


def _valid_e164(phone):
    return bool(re.match(r"^\+[1-9]\d{7,14}$", str(phone or "").strip()))


def _normalize_phone(phone):
    raw = str(phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if raw.startswith("+") and _valid_e164(raw):
        return raw
    if digits.startswith("1") and len(digits) == 11:
        candidate = "+%s" % digits
    elif len(digits) == 10:
        candidate = "+1%s" % digits
    else:
        return ""
    return candidate if _valid_e164(candidate) else ""


def _contact_phone(store, order, *, for_dropoff=False):
    """Uber requires valid E.164 numbers; fall back to the store line for bad customer input."""
    pickup = _normalize_phone(store.phone) or "+12155550100"
    if not for_dropoff:
        return pickup
    dropoff = _normalize_phone(order.customer_phone)
    return dropoff if _valid_e164(dropoff) else pickup


def _uber_address(line1, city, state, zip_code, country="US"):
    payload = {
        "street_address": [str(line1 or "").strip()],
        "city": str(city or "").strip(),
        "state": str(state or "").strip(),
        "zip_code": str(zip_code or "").strip(),
        "country": str(country or "US").strip() or "US",
    }
    return json.dumps(payload, separators=(",", ":"))


def _pickup_address(store):
    return _uber_address(store.address_line, store.city, store.state, store.zip_code)


def _dropoff_address(order):
    return _uber_address(
        order.address_line1 or order.address,
        order.address_city,
        order.address_state,
        order.address_zip,
    )


def _manifest_items(order):
    items = []
    for it in order.items:
        cents = int(round(float(it.unit_price or 0) * 100))
        items.append({
            "name": (it.name or "Item")[:500],
            "quantity": max(1, int(it.qty or 1)),
            "size": "small",
            "price": max(cents, 1),
        })
    if not items:
        items.append({"name": "Order %s" % (order.number or ""), "quantity": 1, "size": "small", "price": 100})
    return items


def _manifest_total_cents(order):
    total = int(round(float(order.subtotal or order.total or 0) * 100))
    return max(total, 100)


def _access_token(cfg):
    client_id = (cfg.get("client_id") or "").strip()
    client_secret = (cfg.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        return None, {"error": "Uber client_id or client_secret missing"}

    cached = _TOKEN_CACHE.get(client_id)
    if cached and cached[1] > time.time() + 60:
        return cached[0], {}

    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "eats.deliveries",
    }).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            data = {"error": exc.reason or "http_%s" % exc.code}
        return None, data
    except Exception as exc:
        return None, {"error": "%s: %s" % (type(exc).__name__, exc)}

    token = data.get("access_token")
    if not token:
        return None, data
    expires = int(data.get("expires_in") or 3600)
    _TOKEN_CACHE[client_id] = (token, time.time() + expires)
    return token, {}


def _api_request(cfg, method, path, body=None):
    token, token_err = _access_token(cfg)
    if not token:
        return {"error": "auth_failed", "details": token_err}

    url = API_BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"error": exc.reason or "http_%s" % exc.code}
        payload["_http_status"] = exc.code
        return payload
    except Exception as exc:
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _delivery_body(store, order, quote_id=None):
    pickup_phone = _contact_phone(store, order, for_dropoff=False)
    dropoff_phone = _contact_phone(store, order, for_dropoff=True)
    body = {
        "pickup_name": store.name,
        "pickup_address": _pickup_address(store),
        "pickup_phone_number": pickup_phone,
        "pickup_business_name": store.name,
        "dropoff_name": order.customer_name or "Customer",
        "dropoff_address": _dropoff_address(order),
        "dropoff_phone_number": dropoff_phone,
        "manifest_items": _manifest_items(order),
        "manifest_total_value": _manifest_total_cents(order),
        "external_id": order.number,
    }
    if quote_id:
        body["quote_id"] = quote_id
    if order.notes:
        body["dropoff_notes"] = str(order.notes)[:280]
    # Tips stay with the restaurant (checkout / payouts); never pass to Uber Direct.
    if order.address_lat and order.address_lng:
        body["dropoff_latitude"] = float(order.address_lat)
        body["dropoff_longitude"] = float(order.address_lng)
    return body


def _quote_body(store, order):
    pickup_phone = _contact_phone(store, order, for_dropoff=False)
    dropoff_phone = _contact_phone(store, order, for_dropoff=True)
    body = {
        "pickup_address": _pickup_address(store),
        "dropoff_address": _dropoff_address(order),
        "pickup_phone_number": pickup_phone,
        "dropoff_phone_number": dropoff_phone,
        "manifest_total_value": _manifest_total_cents(order),
    }
    if order.address_lat and order.address_lng:
        body["dropoff_latitude"] = float(order.address_lat)
        body["dropoff_longitude"] = float(order.address_lng)
    return body


def _tracking_url(delivery):
    return (
        delivery.get("tracking_url")
        or delivery.get("share_url")
        or delivery.get("tracking_link")
        or ""
    )


def _status_from_uber(delivery):
    return map_uber_status(delivery.get("status")) or "assigned"


def map_uber_status(status):
    """Uber Direct status → our delivery.status."""
    s = (status or "").strip().lower()
    return {
        "pending": "pending",
        "pickup": "assigned",
        "courier_assigned": "assigned",
        "en_route_to_pickup": "assigned",
        "pickup_enroute": "assigned",
        "arrived_at_pickup": "assigned",
        "pickup_complete": "picked_up",
        "dropoff": "picked_up",
        "dropoff_enroute": "picked_up",
        "en_route_to_dropoff": "picked_up",
        "delivered": "delivered",
        "canceled": "failed",
        "cancelled": "failed",
        "returned": "failed",
    }.get(s)


def create_delivery(store, order, payload=None):
    """Create a delivery on the store's Uber Direct account."""
    cfg = store_uber_config(store)
    if should_simulate(store, "uber_direct", cfg):
        return {
            "status": "assigned",
            "reference": "uber_%s" % (order.number or "order"),
            "tracking_url": "https://track.uber.example/%s" % (order.number or "order"),
            "raw": {"demo": True, "customer_id": cfg.get("customer_id"), "order": payload},
        }

    customer_id = (cfg.get("customer_id") or "").strip()
    if not is_enabled(store):
        return {
            "status": "failed",
            "reference": None,
            "tracking_url": None,
            "raw": {"error": "Uber Direct credentials missing for production mode"},
        }

    quote = _api_request(
        cfg,
        "POST",
        "/v1/customers/%s/delivery_quotes" % urllib.parse.quote(customer_id, safe=""),
        _quote_body(store, order),
    )
    if quote.get("errors") or quote.get("error") or quote.get("code"):
        return {
            "status": "failed",
            "reference": None,
            "tracking_url": None,
            "raw": {"quote": quote},
        }

    quote_id = quote.get("id") or quote.get("quote_id")
    if not quote_id:
        return {
            "status": "failed",
            "reference": None,
            "tracking_url": None,
            "raw": {"quote": quote, "error": "missing quote id"},
        }

    created = _api_request(
        cfg,
        "POST",
        "/v1/customers/%s/deliveries" % urllib.parse.quote(customer_id, safe=""),
        _delivery_body(store, order, quote_id=quote_id),
    )
    if created.get("errors") or created.get("error") or created.get("code"):
        return {
            "status": "failed",
            "reference": None,
            "tracking_url": None,
            "raw": {"quote": quote, "delivery": created},
        }

    delivery_id = created.get("id") or created.get("delivery_id")
    return {
        "status": _status_from_uber(created),
        "reference": delivery_id,
        "tracking_url": _tracking_url(created),
        "raw": {"quote": quote, "delivery": created},
    }


def cancel_delivery(store, delivery_ref):
    """Cancel an in-flight Uber Direct delivery."""
    cfg = store_uber_config(store)
    if should_simulate(store, "uber_direct", cfg):
        return {
            "status": "simulated",
            "reference": delivery_ref,
            "raw": {"demo": True, "delivery_id": delivery_ref},
        }

    customer_id = (cfg.get("customer_id") or "").strip()
    delivery_ref = (delivery_ref or "").strip()
    if not customer_id or not delivery_ref:
        return {"status": "skipped", "reference": delivery_ref,
                "raw": {"error": "Uber customer_id or delivery id missing"}}

    cancelled = _api_request(
        cfg,
        "POST",
        "/v1/customers/%s/deliveries/%s/cancel" % (
            urllib.parse.quote(customer_id, safe=""),
            urllib.parse.quote(delivery_ref, safe=""),
        ),
        {"reason": "customer_requested"},
    )
    if cancelled.get("errors") or cancelled.get("error"):
        return {"status": "failed", "reference": delivery_ref, "raw": cancelled}
    return {"status": "cancelled", "reference": delivery_ref, "raw": cancelled}


def get_delivery(store, delivery_ref):
    """Fetch current Uber delivery status (for admin/tools)."""
    cfg = store_uber_config(store)
    customer_id = (cfg.get("customer_id") or "").strip()
    delivery_ref = (delivery_ref or "").strip()
    if not customer_id or not delivery_ref:
        return {"error": "missing customer_id or delivery_ref"}
    return _api_request(
        cfg,
        "GET",
        "/v1/customers/%s/deliveries/%s" % (
            urllib.parse.quote(customer_id, safe=""),
            urllib.parse.quote(delivery_ref, safe=""),
        ),
    )
