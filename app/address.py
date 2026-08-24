"""Delivery address formatting and parsing."""


def format_address(line1, line2=None, city=None, state=None, zip_code=None):
    """Build a single-line address for display and legacy fields."""
    street = (line1 or "").strip()
    if line2:
        street = f"{street}, {line2.strip()}".strip(", ")
    tail = ", ".join(p for p in [
        (city or "").strip(),
        " ".join(p for p in [(state or "").strip(), (zip_code or "").strip()] if p),
    ] if p)
    return ", ".join(p for p in [street, tail] if p)


def address_from_form(form):
    """Read structured delivery fields from a werkzeug MultiDict / dict."""
    get = form.get if hasattr(form, "get") else form.__getitem__
    lat = get("address_lat", "").strip()
    lng = get("address_lng", "").strip()
    try:
        lat_f = float(lat) if lat else None
    except (TypeError, ValueError):
        lat_f = None
    try:
        lng_f = float(lng) if lng else None
    except (TypeError, ValueError):
        lng_f = None
    parts = {
        "line1": get("address_line1", "").strip(),
        "line2": get("address_line2", "").strip(),
        "city": get("address_city", "").strip(),
        "state": get("address_state", "").strip(),
        "zip": get("address_zip", "").strip(),
        "lat": lat_f,
        "lng": lng_f,
    }
    parts["one_line"] = format_address(
        parts["line1"], parts["line2"], parts["city"], parts["state"], parts["zip"])
    return parts
