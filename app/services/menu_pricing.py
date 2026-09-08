"""Resolve menu item, variant, and add-on prices for a specific store."""
from decimal import Decimal

from app.models.menu import StoreVariantPrice, StoreAddonPrice


def _variant_overrides(store):
    if not store:
        return {}
    return {
        r.variant_id: float(r.price_delta)
        for r in StoreVariantPrice.query.filter_by(store_id=store.id).all()
    }


def _addon_overrides(store):
    if not store:
        return {}
    return {
        r.addon_id: float(r.price)
        for r in StoreAddonPrice.query.filter_by(store_id=store.id).all()
    }


def variant_delta_for_store(store, variant, overrides=None):
    if not variant:
        return 0.0
    if overrides is None:
        overrides = _variant_overrides(store)
    if variant.id in overrides:
        return overrides[variant.id]
    return float(variant.price_delta or 0)


def addon_price_for_store(store, addon, overrides=None):
    if not addon:
        return 0.0
    if overrides is None:
        overrides = _addon_overrides(store)
    if addon.id in overrides:
        return overrides[addon.id]
    return float(addon.price or 0)


def set_store_variant_delta(store, variant, delta):
    if not store or not variant:
        return
    catalog = float(variant.price_delta or 0)
    value = float(delta or 0)
    row = StoreVariantPrice.query.filter_by(store_id=store.id, variant_id=variant.id).first()
    if abs(value - catalog) < 0.001:
        if row:
            from app.extensions import db
            db.session.delete(row)
        return
    from app.extensions import db
    if not row:
        row = StoreVariantPrice(store_id=store.id, variant_id=variant.id)
        db.session.add(row)
    row.price_delta = Decimal(str(round(value, 2)))


def set_store_addon_price(store, addon, price):
    if not store or not addon:
        return
    catalog = float(addon.price or 0)
    value = float(price or 0)
    row = StoreAddonPrice.query.filter_by(store_id=store.id, addon_id=addon.id).first()
    if abs(value - catalog) < 0.001:
        if row:
            from app.extensions import db
            db.session.delete(row)
        return
    from app.extensions import db
    if not row:
        row = StoreAddonPrice(store_id=store.id, addon_id=addon.id)
        db.session.add(row)
    row.price = Decimal(str(round(value, 2)))


def library_addon_price_for_store(store, lib, links=None, overrides=None):
    """Resolved display price for a shared library entry at one location."""
    if not store:
        return float(lib.price or 0)
    if overrides is None:
        overrides = _addon_overrides(store)
    if links is None:
        from app.models.menu import ProductAddon
        links = ProductAddon.query.filter_by(library_id=lib.id).all()
    for link in links:
        if link.id in overrides:
            return overrides[link.id]
    if links:
        return float(links[0].price or lib.price or 0)
    return float(lib.price or 0)


def set_store_library_addon_prices(store, lib, price):
    """Apply a per-location price to every product link for this library entry."""
    if not store or not lib:
        return
    from app.models.menu import ProductAddon
    for link in ProductAddon.query.filter_by(library_id=lib.id).all():
        set_store_addon_price(store, link, price)
