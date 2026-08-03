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
