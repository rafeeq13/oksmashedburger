"""Per-location promotional image banners (admin-configured)."""
import json
import re

from app.extensions import db
from app.models.site import SiteSetting
from app.services.promo_page_targets import normalize_show_pages, promo_shown_on_path

GLOBAL_SETTING_KEY = "promo_banner"
SETTING_KEY = GLOBAL_SETTING_KEY  # backwards compat
# On-page editor (?edit=1) tags banner pictures with this slot key.
INLINE_IMAGE_KEY = "promo_banner_image"

PROMO_IMAGE_SPEC = {"build_size": "2800×440"}

DEFAULT_PROMO_BANNER = {
    "enabled": True,
    "placement": "visit_popup",
    "height": 88,
    "width": "container",
    "use_image": True,
    "image": (
        "https://images.unsplash.com/photo-1550547660-d9450f859349"
        "?w=1400&h=280&fit=crop&q=80"
    ),
    "image_position": "center center",
    "bg_color": "#f5c518",
    "link": "/deals",
    "show_deals_link": True,
    "text": "Exclusive deals — tap to save",
    "text_color": "#ffffff",
    "text_size": 15,
    "text_font": "",
    "show_text": True,
    "overlay": 0.45,
    "border_style": "blink",
    "show_subscribe": False,
    "subscribe_label": "Get deals",
    "subscribe_border_color": "#ffffff",
    "subscribe_input_color": "#ffffff",
    "subscribe_bar_bg_color": "#0c0c0c",
    "subscribe_bar_transparent": False,
    "deals_link_color": "#f5c518",
    "subscribe_placeholder_color": "#ffffff",
    "subscribe_btn_text_color": "#141414",
    "subscribe_btn_bg_color": "#f5c518",
    "deals_link_size": 15,
    "subscribe_input_size": 16,
    "subscribe_btn_size": 13,
    "deals_btn_text_color": "#111111",
    "mobile_text_size": 11,
    "mobile_deals_link_size": 11,
    "mobile_subscribe_input_size": 13,
    "mobile_subscribe_btn_size": 11,
    "popup_close_size": 36,
    "popup_close_bg_color": "#ffffff",
    "popup_close_color": "#111111",
    "popup_modal_width_px": 360,
    "popup_modal_min_height_px": 400,
    "popup_join_width_px": 0,
    "popup_subscribe_gap_px": 0,
    "popup_field_height_px": 44,
    "popup_btn_height_px": 44,
    "popup_btn_min_width_px": 100,
    "popup_email_width_pct": 82,
    "popup_subscribe_join_bg": True,
}

_PLACEMENTS = frozenset({"visit_popup", "above_header", "below_header", "above_footer"})
_WIDTHS = frozenset({"full", "container"})
_BORDER_STYLES = frozenset({"none", "static", "blink"})


def setting_key_for_store(store):
    """SiteSetting key for one location's banner override (or brand default)."""
    if store and getattr(store, "slug", None):
        return f"promo_banner__{store.slug}"
    return GLOBAL_SETTING_KEY


def _clamp_int(val, default, lo, hi):
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clamp_float(val, default, lo, hi):
    try:
        n = float(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _hex_color(raw, default):
    val = (raw or default or "").strip()
    if not re.match(r"^#[0-9A-Fa-f]{3,8}$", val):
        return default
    return val


def normalize_promo_banner(raw):
    """Merge saved dict with defaults and coerce types."""
    raw_dict = raw if isinstance(raw, dict) else {}
    legacy_pages = "show_pages" not in raw_dict
    base = dict(DEFAULT_PROMO_BANNER)
    if raw_dict:
        base.update(raw_dict)
    placement = (base.get("placement") or "visit_popup").strip()
    if placement == "above_header":
        placement = "visit_popup"
    if placement not in _PLACEMENTS:
        placement = "visit_popup"
    width = (base.get("width") or "container").strip()
    if width not in _WIDTHS:
        width = "container"
    use_image = bool(base.get("use_image", True))
    image = (base.get("image") or "").strip()
    if use_image and not image:
        image = DEFAULT_PROMO_BANNER["image"]
    bg_color = (base.get("bg_color") or DEFAULT_PROMO_BANNER["bg_color"]).strip()
    if not re.match(r"^#[0-9A-Fa-f]{3,8}$", bg_color):
        bg_color = DEFAULT_PROMO_BANNER["bg_color"]
    border_style = (base.get("border_style") or "").strip().lower()
    if border_style not in _BORDER_STYLES:
        border_style = "blink" if base.get("blink_border", True) else "none"
    link = (base.get("link") or "/deals").strip() or "/deals"
    if link.startswith("/") or link.startswith("http://") or link.startswith("https://"):
        pass
    else:
        link = "/" + link.lstrip("/")
    text = (base.get("text") or "").strip() or DEFAULT_PROMO_BANNER["text"]
    text_color = _hex_color(base.get("text_color"), DEFAULT_PROMO_BANNER["text_color"])
    img_pos = (base.get("image_position") or "center center").strip()[:80]
    text_font = (base.get("text_font") or "").strip()[:400]
    subscribe_label = (base.get("subscribe_label") or DEFAULT_PROMO_BANNER["subscribe_label"]).strip()
    subscribe_label = subscribe_label[:40] or DEFAULT_PROMO_BANNER["subscribe_label"]
    subscribe_border_color = _hex_color(
        base.get("subscribe_border_color"), DEFAULT_PROMO_BANNER["subscribe_border_color"]
    )
    subscribe_input_color = _hex_color(
        base.get("subscribe_input_color"), DEFAULT_PROMO_BANNER["subscribe_input_color"]
    )
    subscribe_bar_bg_color = _hex_color(
        base.get("subscribe_bar_bg_color"), DEFAULT_PROMO_BANNER["subscribe_bar_bg_color"]
    )
    deals_link_color = _hex_color(base.get("deals_link_color"), DEFAULT_PROMO_BANNER["deals_link_color"])
    deals_btn_text_color = _hex_color(
        base.get("deals_btn_text_color"), DEFAULT_PROMO_BANNER["deals_btn_text_color"]
    )
    subscribe_placeholder_color = _hex_color(
        base.get("subscribe_placeholder_color"), DEFAULT_PROMO_BANNER["subscribe_placeholder_color"]
    )
    subscribe_btn_text_color = _hex_color(
        base.get("subscribe_btn_text_color"), DEFAULT_PROMO_BANNER["subscribe_btn_text_color"]
    )
    subscribe_btn_bg_color = _hex_color(
        base.get("subscribe_btn_bg_color"), DEFAULT_PROMO_BANNER["subscribe_btn_bg_color"]
    )
    popup_close_bg_color = _hex_color(
        base.get("popup_close_bg_color"), DEFAULT_PROMO_BANNER["popup_close_bg_color"]
    )
    popup_close_color = _hex_color(
        base.get("popup_close_color"), DEFAULT_PROMO_BANNER["popup_close_color"]
    )
    if "show_deals_link" in raw_dict:
        show_deals_link = bool(base.get("show_deals_link"))
    else:
        show_deals_link = bool(DEFAULT_PROMO_BANNER["show_deals_link"])
    popup_modal_width_px = _clamp_int(
        base.get("popup_modal_width_px"), DEFAULT_PROMO_BANNER["popup_modal_width_px"], 280, 520
    )
    popup_join_width_px = _clamp_int(base.get("popup_join_width_px"), 0, 0, 520)
    return {
        "enabled": bool(base.get("enabled", True)),
        "placement": placement,
        "height": _clamp_int(base.get("height"), DEFAULT_PROMO_BANNER["height"], 16, 220),
        "width": width,
        "use_image": use_image,
        "image": image[:2000] if use_image else "",
        "image_position": img_pos,
        "bg_color": bg_color,
        "link": link[:500],
        "show_deals_link": show_deals_link,
        "text": text[:240],
        "text_color": text_color,
        "text_size": _clamp_int(base.get("text_size"), 15, 10, 48),
        "text_font": text_font,
        "show_text": bool(base.get("show_text", True)),
        "overlay": _clamp_float(base.get("overlay"), 0.45, 0.0, 0.85),
        "border_style": border_style,
        "blink_border": border_style == "blink",
        "show_subscribe": bool(base.get("show_subscribe", False)),
        "subscribe_label": subscribe_label,
        "subscribe_border_color": subscribe_border_color,
        "subscribe_input_color": subscribe_input_color,
        "subscribe_bar_bg_color": subscribe_bar_bg_color,
        "subscribe_bar_transparent": bool(base.get("subscribe_bar_transparent", False)),
        "deals_link_color": deals_link_color,
        "deals_btn_text_color": deals_btn_text_color,
        "deals_link_size": _clamp_int(base.get("deals_link_size"), 15, 8, 32),
        "subscribe_input_size": _clamp_int(base.get("subscribe_input_size"), 16, 8, 32),
        "subscribe_btn_size": _clamp_int(base.get("subscribe_btn_size"), 13, 8, 32),
        "subscribe_placeholder_color": subscribe_placeholder_color,
        "subscribe_btn_text_color": subscribe_btn_text_color,
        "subscribe_btn_bg_color": subscribe_btn_bg_color,
        "mobile_text_size": _clamp_int(base.get("mobile_text_size"), 11, 8, 28),
        "mobile_deals_link_size": _clamp_int(base.get("mobile_deals_link_size"), 11, 8, 28),
        "mobile_subscribe_input_size": _clamp_int(base.get("mobile_subscribe_input_size"), 13, 8, 28),
        "mobile_subscribe_btn_size": _clamp_int(base.get("mobile_subscribe_btn_size"), 11, 8, 28),
        "popup_close_size": _clamp_int(base.get("popup_close_size"), 36, 24, 56),
        "popup_close_bg_color": popup_close_bg_color,
        "popup_close_color": popup_close_color,
        "show_pages": normalize_show_pages(base.get("show_pages"), legacy_default_all=legacy_pages),
        "popup_modal_width_px": popup_modal_width_px,
        "popup_modal_min_height_px": _clamp_int(base.get("popup_modal_min_height_px"), 400, 280, 640),
        "popup_join_width_px": popup_join_width_px,
        "popup_subscribe_gap_px": _clamp_int(base.get("popup_subscribe_gap_px"), 0, 0, 16),
        "popup_field_height_px": _clamp_int(base.get("popup_field_height_px"), 44, 32, 72),
        "popup_btn_height_px": _clamp_int(base.get("popup_btn_height_px"), 44, 32, 72),
        "popup_btn_min_width_px": _clamp_int(base.get("popup_btn_min_width_px"), 100, 72, 220),
        "popup_email_width_pct": _clamp_int(base.get("popup_email_width_pct"), 82, 52, 92),
        "popup_subscribe_join_bg": bool(base.get("popup_subscribe_join_bg", True)),
    }


def _read_setting_raw(key):
    row = SiteSetting.query.filter_by(key=key).first()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_setting(key, normalized):
    payload = json.dumps(normalized, separators=(",", ":"))
    row = SiteSetting.query.filter_by(key=key).first()
    if row:
        row.value = payload
    else:
        db.session.add(SiteSetting(key=key, value=payload))
    db.session.commit()
    return normalized


def store_has_banner_override(store):
    if not store or not getattr(store, "slug", None):
        return False
    row = SiteSetting.query.filter_by(key=setting_key_for_store(store)).first()
    return bool(row and row.value)


def load_promo_banner(store=None):
    """Effective banner for a storefront location (store override + brand default)."""
    global_raw = _read_setting_raw(GLOBAL_SETTING_KEY)
    merged = dict(global_raw)
    if store and getattr(store, "slug", None):
        store_raw = _read_setting_raw(setting_key_for_store(store))
        if store_raw:
            merged.update(store_raw)
    return normalize_promo_banner(merged)


def load_promo_banner_global():
    """Brand-default banner only (admin screen without a location)."""
    return normalize_promo_banner(_read_setting_raw(GLOBAL_SETTING_KEY))


def save_promo_banner(cfg, store=None):
    """Save brand default (store=None) or a location's full override."""
    normalized = normalize_promo_banner(cfg)
    key = setting_key_for_store(store)
    return _write_setting(key, normalized)


def clear_store_promo_banner(store):
    if not store or not getattr(store, "slug", None):
        return False
    row = SiteSetting.query.filter_by(key=setting_key_for_store(store)).first()
    if not row:
        return False
    db.session.delete(row)
    db.session.commit()
    return True


def _promo_banner_has_content(cfg):
    has_image = cfg.get("use_image") and (cfg.get("image") or "").strip()
    has_text = cfg.get("show_text") and (cfg.get("text") or "").strip()
    has_sub = bool(cfg.get("show_subscribe"))
    return bool(has_image or has_text or has_sub)


def _promo_banner_base_ok(cfg, features, path, inline_edit=False):
    if inline_edit:
        return True
    if not features.get("deals"):
        return False
    if not cfg.get("enabled"):
        return False
    if (path or "").startswith("/admin"):
        return False
    if not _promo_banner_has_content(cfg):
        return False
    return True


def promo_banner_visible(cfg, features, path, inline_edit=False):
    if not _promo_banner_base_ok(cfg, features, path, inline_edit=inline_edit):
        return False
    if inline_edit:
        return True
    if not promo_shown_on_path(cfg.get("show_pages"), path):
        return False
    return True


def _visit_popup_cfg_for_store(features, store=None):
    cfg = load_promo_banner(store)
    if not _promo_banner_base_ok(cfg, features, "/", inline_edit=False):
        return None
    if cfg.get("placement") != "visit_popup":
        return None
    return cfg


def promo_visit_popup_any_cfg(features):
    """Brand default or any active location with a visit popup configured."""
    cfg = _visit_popup_cfg_for_store(features, None)
    if cfg:
        return cfg
    from app.models.store import Store

    for store in Store.query.filter_by(is_active=True).order_by(Store.id).all():
        cfg = _visit_popup_cfg_for_store(features, store)
        if cfg:
            return cfg
    return None


def promo_visit_popup_before_location(cfg, features, needs_location=False, inline_edit=False):
    """Include visit-popup markup on first visit so it can open right after store pick."""
    if inline_edit or not needs_location:
        return False
    if _promo_banner_base_ok(cfg, features, "/", inline_edit=False) and cfg.get("placement") == "visit_popup":
        return True
    return promo_visit_popup_any_cfg(features) is not None


def promo_banner_on_request(cfg, features, path, needs_location=False, inline_edit=False):
    if promo_banner_visible(cfg, features, path, inline_edit=inline_edit):
        return True
    return promo_visit_popup_before_location(
        cfg, features, needs_location=needs_location, inline_edit=inline_edit
    )


def promo_banner_after_location_pick(cfg, features):
    """Visit popup right after the customer picks a store (any page, incl. home)."""
    return _visit_popup_cfg_for_store(features, None) is not None or (
        _promo_banner_base_ok(cfg, features, "/", inline_edit=False)
        and cfg.get("placement") == "visit_popup"
    )


def deals_visit_popup_partial_context():
    """Template context for the visit popup fragment, or None if it should not show."""
    from flask import request, session

    from app.helpers import get_current_store
    from app.models.site import SiteSetting, features_from

    store = get_current_store()
    if not store or not session.get("context_set"):
        return None
    rows = {r.key: r.value for r in SiteSetting.query.all() if r.value}
    feats = features_from(rows)
    cfg = load_promo_banner(store)
    if not promo_banner_after_location_pick(cfg, feats):
        return None
    banner = dict(cfg)
    banner["store_slug"] = store.slug
    banner["store_name"] = store.name
    banner["auto_open_on_page"] = promo_shown_on_path(banner.get("show_pages"), request.path)
    return {
        "promo_banner": banner,
        "current_store": store,
        "inline_edit": False,
    }


def set_promo_banner_image(url, store=None):
    """Set banner image URL from inline editor or admin (current location if store set)."""
    cfg = load_promo_banner(store) if store else load_promo_banner_global()
    cleaned = (url or "").strip()
    cfg = dict(cfg)
    cfg["use_image"] = True
    cfg["image"] = cleaned if cleaned else DEFAULT_PROMO_BANNER["image"]
    return save_promo_banner(cfg, store=store)


_INLINE_SCALAR = frozenset({
    "text", "link", "placement", "width", "image_position", "border_style",
    "text_font", "bg_color", "text_color", "subscribe_label",
    "subscribe_border_color", "subscribe_input_color", "subscribe_bar_bg_color",
    "deals_link_color", "deals_btn_text_color", "subscribe_placeholder_color",
    "subscribe_btn_text_color", "subscribe_btn_bg_color",
    "popup_close_bg_color", "popup_close_color",
})
_INLINE_BOOL = frozenset({
    "enabled", "show_text", "use_image", "blink_border", "show_subscribe",
    "subscribe_bar_transparent",
})
_INLINE_INT = frozenset({
    "height", "text_size", "deals_link_size", "subscribe_input_size", "subscribe_btn_size",
    "mobile_text_size", "mobile_deals_link_size",
    "mobile_subscribe_input_size", "mobile_subscribe_btn_size",
    "popup_close_size",
})
_INLINE_FLOAT = frozenset({"overlay"})


def update_promo_banner_field(field, value, store=None):
    """One field from the on-page design panel or inline text edit."""
    field = (field or "").strip()
    if field not in _INLINE_SCALAR | _INLINE_BOOL | _INLINE_INT | _INLINE_FLOAT:
        raise ValueError("unknown field")
    if store:
        cfg = load_promo_banner(store)
    else:
        cfg = load_promo_banner_global()
    cfg = dict(cfg)
    if field == "blink_border":
        cfg["border_style"] = "blink" if (
            bool(value) if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
        ) else "none"
    elif field in _INLINE_BOOL:
        cfg[field] = bool(value) if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
    elif field in _INLINE_INT:
        cfg[field] = value
    elif field in _INLINE_FLOAT:
        cfg[field] = value
    else:
        cfg[field] = (value or "").strip() if value is not None else ""
    return save_promo_banner(cfg, store=store)
