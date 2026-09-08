"""Small shared helpers used by blueprints and template context."""
import os

from flask import session
from .models.store import Store


def active_stores():
    return Store.query.filter_by(is_active=True).order_by(Store.name).all()


def get_current_store():
    """The store the visitor is ordering from (session-selected, else first)."""
    q = Store.query.filter_by(is_active=True)
    slug = session.get("store_slug")
    if slug:
        s = q.filter_by(slug=slug).first()
        if s:
            return s
    return q.order_by(Store.name).first()


def store_accepts_order_type(store, order_type):
    if not store:
        return order_type in ("delivery", "pickup")
    if order_type == "delivery":
        return bool(store.accepts_delivery)
    if order_type == "pickup":
        return bool(store.accepts_pickup)
    return False


def allowed_order_types(store):
    if not store:
        return ["delivery", "pickup"]
    allowed = []
    if store.accepts_delivery:
        allowed.append("delivery")
    if store.accepts_pickup:
        allowed.append("pickup")
    return allowed


def normalize_order_type(store=None, order_type=None):
    """Keep session order type valid for the current store's pickup/delivery flags."""
    store = store or get_current_store()
    allowed = allowed_order_types(store)
    if not allowed:
        if session.get("order_type") is not None:
            session.pop("order_type", None)
            session.modified = True
        return None
    ot = order_type if order_type is not None else session.get("order_type", allowed[0])
    if ot not in allowed:
        ot = allowed[0]
    if session.get("order_type") != ot:
        session["order_type"] = ot
        session.modified = True
    return ot


def get_order_type():
    return normalize_order_type()


def fulfillment_available(store=None):
    return bool(allowed_order_types(store or get_current_store()))


def store_location_locked():
    """Cart → checkout → confirmation only: lock while the customer is on those pages."""
    from flask import request

    locked = {"/cart", "/checkout", "/order-confirmed"}
    path = (request.path or "").rstrip("/") or "/"
    return path in locked


def public_site_url(path=""):
    """Canonical public site URL for emails, webhooks, and CLI tools."""
    import os

    path = path or ""
    if path and not path.startswith("/"):
        path = "/" + path
    try:
        from flask import has_request_context, url_for

        if has_request_context():
            return url_for("website.home", _external=True).rstrip("/") + path
    except Exception:
        pass
    try:
        from flask import current_app

        base = (current_app.config.get("PUBLIC_SITE_URL") or "").strip().rstrip("/")
        if base:
            return base + path
    except Exception:
        pass
    base = os.environ.get("PUBLIC_SITE_URL", "https://oksmashedburger.com").strip().rstrip("/")
    return base + path


_asset_mtimes = {}


def versioned_asset_url(url):
    """Append ?v=<mtime> to /static/ paths (uploads, etc.) for cache busting."""
    if not url:
        return url
    url = str(url).strip()
    if url.startswith(("http://", "https://", "//", "data:", "blob:")):
        return url
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    path = parts.path
    if not path.startswith("/static/"):
        return url
    rel = path[len("/static/") :].lstrip("/")
    try:
        from flask import current_app

        full = os.path.join(current_app.static_folder, rel.replace("/", os.sep))
        stamp = _asset_mtimes.get(full)
        if stamp is None:
            stamp = int(os.stat(full).st_mtime)
            _asset_mtimes[full] = stamp
    except (OSError, RuntimeError):
        return url
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "v"]
    query.append(("v", str(stamp)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def order_dt_local(order, field="created_at"):
    """Convert an order datetime field to the store's local timezone."""
    from datetime import timezone
    from zoneinfo import ZoneInfo

    dt = getattr(order, field, None)
    if not dt:
        return None
    store = getattr(order, "store", None)
    tz_name = (store.timezone if store else None) or "America/New_York"
    tz = None
    for name in (tz_name, "America/New_York", "UTC"):
        try:
            tz = ZoneInfo(name)
            break
        except Exception:
            continue
    if tz is None:
        tz = timezone.utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def feature_on(name):
    """True when a site feature switch is on (absent row = on)."""
    from app.models.site import SiteSetting, features_from

    rows = {r.key: r.value for r in SiteSetting.query.all() if r.value}
    return features_from(rows).get(name, True)


def coupons_for_store(store):
    """Active deals visible at a store (location-specific + all-locations)."""
    from sqlalchemy import or_

    from app.models.promo import Coupon

    q = Coupon.query.filter_by(active=True)
    if not store:
        return []
    q = q.filter(or_(Coupon.store_id.is_(None), Coupon.store_id == store.id))
    return q.order_by(Coupon.created_at.desc()).all()


def coupon_public_dict(coupon):
    """JSON-safe deal card fields for /api/deals."""
    exp = None
    if coupon.expires_at:
        exp = coupon.expires_at.strftime("%b %d")
    return {
        "code": coupon.code,
        "description": coupon.description or coupon.code,
        "kind": coupon.kind,
        "value": float(coupon.value or 0),
        "min_order": float(coupon.min_order or 0),
        "requires_code": bool(coupon.requires_code),
        "image_url": versioned_asset_url(coupon.image_url or ""),
        "expires_at": exp,
    }


FOOTER_SOCIAL_DEFS = (
    ("instagram", "fa-brands fa-instagram", "@oksmashedburger", "Instagram"),
    ("facebook", "fa-brands fa-facebook-f", "oksmashedburger", "Facebook"),
    ("tiktok", "fa-brands fa-tiktok", "@oksmashedburger", "TikTok"),
    ("youtube", "fa-brands fa-youtube", "@oksmashedburger", "YouTube"),
    ("google", "fa-brands fa-google", "Google Reviews", "Google"),
)


def footer_social_links():
    """Social profile links for the site footer and contact page."""
    from flask import current_app
    from app.models.email_templates import DEFAULT_SOCIAL_URLS, social_urls

    brand = current_app.config.get("BRAND_NAME", "OK Smashed Burger")
    urls = social_urls(brand)
    out = []
    for key, icon, handle, label in FOOTER_SOCIAL_DEFS:
        url = urls.get(key) or DEFAULT_SOCIAL_URLS.get(key, "")
        if url:
            out.append({"key": key, "url": url, "icon": icon, "handle": handle, "label": label})
    return out


def find_store_for_zip(zip_code):
    """Nearest location for a ZIP: the store whose delivery zone lists it, else
    the first open store, else the first active store."""
    zip_code = (zip_code or "").strip()
    stores = active_stores()
    if zip_code:
        for s in stores:
            for z in s.delivery_zones:
                if zip_code in (z.zip_codes or []):
                    return s
        # loose match: same 3-digit ZIP prefix counts as nearby
        for s in stores:
            if s.zip_code and s.zip_code[:3] == zip_code[:3]:
                return s
    return next((s for s in stores if s.open_now), stores[0] if stores else None)


def product_modifier_sections(product, store=None, variants_label="Choose your size", addons_label="Add-ons"):
    """Ordered modifier blocks for the item page / quick-add popup."""
    from app.services.menu_pricing import variant_delta_for_store, addon_price_for_store, _variant_overrides, _addon_overrides
    variant_ov = _variant_overrides(store)
    addon_ov = _addon_overrides(store)
    sections = []
    if product.variants:
        sections.append({
            "kind": "variants",
            "label": (product.variants_section_label or "").strip() or variants_label,
            "order": product.variants_section_order if product.variants_section_order is not None else 0,
            "variants": [{
                "id": v.id,
                "name": v.name,
                "price_delta": variant_delta_for_store(store, v, variant_ov),
                "is_default": v.is_default,
            } for v in product.variants],
        })
    groups = {}
    for addon in product.addons:
        if addon.section:
            key = f"sec:{addon.section_id}"
            label = addon.section.label
            order = addon.section.sort_order or 0
        else:
            label = (addon.group_label or "").strip() or addons_label
            key = f"lbl:{label}"
            order = addon.sort_order or 0
        if key not in groups:
            groups[key] = {"kind": "addons", "label": label, "order": order, "addons": []}
        groups[key]["addons"].append({
            "id": addon.id,
            "name": addon.name,
            "price": addon_price_for_store(store, addon, addon_ov),
            "is_required": addon.is_required,
            "sort_order": addon.sort_order or 0,
        })
        groups[key]["order"] = min(groups[key]["order"], order)
    for group in groups.values():
        group["addons"].sort(key=lambda a: (a["sort_order"], a["id"]))
        sections.append(group)
    sections.sort(key=lambda s: (s["order"], 0 if s["kind"] == "variants" else 1, s["label"]))
    return sections
