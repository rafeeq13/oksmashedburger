"""Match customer addresses to store delivery zones and fees."""
import math
import re

_ZIP_DIGITS = re.compile(r"\d+")


def normalize_zip(zip_code):
    digits = "".join(_ZIP_DIGITS.findall(zip_code or ""))
    return digits[:5] if len(digits) >= 5 else digits


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _zone_zip_match(zone, zip_code):
    nz = normalize_zip(zip_code)
    if not nz:
        return False
    for raw in zone.zip_codes or []:
        if normalize_zip(raw) == nz:
            return True
    return False


def _zone_distance_match(zone, distance_miles):
    if distance_miles is None:
        return False
    radius = float(zone.radius_miles or 0)
    return radius > 0 and distance_miles <= radius


def _fallback_zone_fee(store):
    pool = [z for z in store.delivery_zones if z.is_active] or list(store.delivery_zones)
    if pool:
        zone = min(pool, key=lambda z: (z.radius_miles or 0))
        return float(zone.delivery_fee or 0), zone
    return 2.99, None


def _address_label(address_label=None, line1=None, line2=None, city=None, state=None, zip_code=None, search=None):
    """Human-readable address for delivery zone messages."""
    if address_label:
        return str(address_label).strip()
    if search:
        return str(search).strip()
    from app.address import format_address
    label = format_address(line1, line2, city, state, zip_code)
    if label:
        return label
    nz = normalize_zip(zip_code)
    return ("ZIP %s" % nz) if nz else ""


def match_delivery_zone(store, zip_code=None, lat=None, lng=None, address_label=None,
                        line1=None, line2=None, city=None, state=None, search=None):
    """Resolve the delivery zone for an address at the selected store.

    Returns a dict with in_zone, zone, delivery_fee, min_order, est_minutes,
    distance_miles, and a user-facing message when out of zone.
    """
    if not store:
        return _out_of_zone("No store selected.")

    addr = _address_label(address_label, line1, line2, city, state, zip_code, search)

    active = [z for z in store.delivery_zones if z.is_active]
    pool = sorted(active or list(store.delivery_zones), key=lambda z: (z.radius_miles or 0))

    if not pool:
        fee, _zone = _fallback_zone_fee(store)
        min_order = float(store.min_order_amount or 10)
        return {
            "in_zone": True,
            "zone": None,
            "zone_id": None,
            "zone_name": "Standard",
            "delivery_fee": fee,
            "min_order": min_order,
            "est_minutes": 30,
            "distance_miles": None,
            "message": "",
            "address_label": addr,
        }

    nz = normalize_zip(zip_code)
    distance = None
    if lat is not None and lng is not None and store.latitude is not None and store.longitude is not None:
        distance = haversine_miles(store.latitude, store.longitude, lat, lng)

    has_zip_lists = any(z.zip_codes for z in pool)
    candidates = []
    for zone in pool:
        if _zone_zip_match(zone, nz) or _zone_distance_match(zone, distance):
            candidates.append(zone)

    if candidates:
        zone = min(candidates, key=lambda z: (z.radius_miles or 0))
        min_order = zone.min_order if zone.min_order is not None else store.min_order_amount
        return {
            "in_zone": True,
            "zone": zone,
            "zone_id": zone.id,
            "zone_name": zone.name or "Delivery",
            "delivery_fee": float(zone.delivery_fee or 0),
            "min_order": float(min_order or 0),
            "est_minutes": int(zone.est_minutes or 30),
            "distance_miles": round(distance, 2) if distance is not None else None,
            "message": "",
            "address_label": addr,
        }

    if not nz and distance is None:
        return _out_of_zone(
            "Enter your full delivery address to check if we deliver to you.",
            store=store,
            address_label=addr,
        )

    if nz and has_zip_lists and distance is None:
        where = addr or ("ZIP %s" % nz)
        msg = (
            "Sorry, we can't deliver to %s from %s. "
            "Try pickup or choose a closer location."
            % (where, store.name)
        )
    elif distance is not None:
        max_r = max((z.radius_miles or 0) for z in pool)
        where = addr or "that address"
        msg = (
            "Sorry, we can't deliver to %s. This address is outside our delivery area "
            "(%g mi from %s). Try pickup instead."
            % (where, max_r, store.name)
        )
    elif nz:
        where = addr or ("ZIP %s" % nz)
        msg = "Sorry, we can't deliver to %s from %s." % (where, store.name)
    else:
        where = addr or "that address"
        msg = "Sorry, we can't deliver to %s." % where

    return _out_of_zone(msg, store=store, address_label=addr)


def _out_of_zone(message, store=None, address_label=""):
    return {
        "in_zone": False,
        "zone": None,
        "zone_id": None,
        "zone_name": None,
        "delivery_fee": 0.0,
        "min_order": float(store.min_order_amount or 10) if store else 10.0,
        "est_minutes": None,
        "distance_miles": None,
        "message": message,
        "address_label": address_label or "",
    }
