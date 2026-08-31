"""Small shared helpers used by blueprints and template context."""
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


def get_order_type():
    return session.get("order_type", "delivery")


def feature_on(key):
    """site_settings check for a feature_XXX switch (defaults to ON)."""
    from .models.site import SiteSetting
    if not key.startswith("feature_"):
        key = "feature_" + key
    row = SiteSetting.query.filter_by(key=key).first()
    return (row.value if row else "on") != "off"


def order_dt_local(order, field="created_at"):
    """Convert an order datetime field to the store's local timezone."""
    from datetime import timezone
    from zoneinfo import ZoneInfo

    dt = getattr(order, field, None)
    if not dt:
        return None
    store = getattr(order, "store", None)
    tz_name = (store.timezone if store else None) or "America/New_York"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)

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
        "image_url": coupon.image_url or "",
        "expires_at": exp,
    }


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


def product_modifier_sections(product, variants_label="Choose your size", addons_label="Add-ons"):
    """Ordered modifier blocks for the item page / quick-add popup."""
    sections = []
    if product.variants:
        sections.append({
            "kind": "variants",
            "label": (product.variants_section_label or "").strip() or variants_label,
            "order": product.variants_section_order if product.variants_section_order is not None else 0,
            "variants": list(product.variants),
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
        groups[key]["addons"].append(addon)
        groups[key]["order"] = min(groups[key]["order"], order)
    for group in groups.values():
        group["addons"].sort(key=lambda a: (a.sort_order or 0, a.id))
        sections.append(group)
    sections.sort(key=lambda s: (s["order"], 0 if s["kind"] == "variants" else 1, s["label"]))
    return sections
