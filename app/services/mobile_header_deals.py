"""Mobile promo image strip shown below the site header (phones only)."""
import json
from app.extensions import db
from app.models.site import SiteSetting
from app.services.promo_page_targets import normalize_show_pages, promo_shown_on_path

SETTING_KEY = "mobile_header_deals"
# Matches logo height in header (.ok-h-11) inside the 4rem mobile bar (.ok-h-16).
MOBILE_STRIP_DEFAULT_WIDTH_PX = 1200
MOBILE_STRIP_DEFAULT_HEIGHT_PX = 72
CHIP_IMAGE_SPEC = {"build_size": "780×144"}

DEFAULT = {
    "enabled": False,
    "image": "",
    "width_px": MOBILE_STRIP_DEFAULT_WIDTH_PX,
    "height_px": MOBILE_STRIP_DEFAULT_HEIGHT_PX,
    "link": "/deals",
    "blink_enabled": True,
    "blink_duration_s": 1.15,
}


def _blink_duration(val):
    try:
        n = float(val)
    except (TypeError, ValueError):
        n = DEFAULT["blink_duration_s"]
    return round(max(0.4, min(3.0, n)), 2)


def normalize(raw):
    raw_dict = raw if isinstance(raw, dict) else {}
    legacy_pages = "show_pages" not in raw_dict
    base = dict(DEFAULT)
    if raw_dict:
        base.update(raw_dict)
    link = (base.get("link") or "/deals").strip() or "/deals"
    if not link.startswith("/") and not link.startswith("http"):
        link = "/" + link.lstrip("/")
    image = (base.get("image") or "").strip()[:2000]
    try:
        width = int(base.get("width_px", DEFAULT["width_px"]))
    except (TypeError, ValueError):
        width = DEFAULT["width_px"]
    if 0 < width < 100:
        width = MOBILE_STRIP_DEFAULT_WIDTH_PX
    width = max(280, min(1200, width))
    try:
        height = int(base.get("height_px", base.get("display_height_px", DEFAULT["height_px"])))
    except (TypeError, ValueError):
        height = DEFAULT["height_px"]
    height = max(32, min(240, height))
    return {
        "enabled": bool(base.get("enabled")),
        "image": image,
        "width_px": width,
        "height_px": height,
        "link": link[:500],
        "blink_enabled": bool(base.get("blink_enabled", True)),
        "blink_duration_s": _blink_duration(base.get("blink_duration_s")),
        "show_pages": normalize_show_pages(base.get("show_pages"), legacy_default_all=legacy_pages),
        "display_height_px": height,
        "display_size": "%d×%d" % (width, height),
        "upload_size": "%d×%d" % (width * 2, height * 2),
    }


def load_mobile_header_deals():
    row = SiteSetting.query.filter_by(key=SETTING_KEY).first()
    if not row or not row.value:
        return normalize({})
    try:
        data = json.loads(row.value)
    except Exception:
        return normalize({})
    return normalize(data if isinstance(data, dict) else {})


def save_mobile_header_deals(cfg):
    normalized = normalize(cfg)
    persist = {
        "enabled": normalized["enabled"],
        "image": normalized["image"],
        "width_px": normalized["width_px"],
        "height_px": normalized["height_px"],
        "link": normalized["link"],
        "blink_enabled": normalized["blink_enabled"],
        "blink_duration_s": normalized["blink_duration_s"],
        "show_pages": normalized["show_pages"],
    }
    payload = json.dumps(persist, separators=(",", ":"))
    row = SiteSetting.query.filter_by(key=SETTING_KEY).first()
    if row:
        row.value = payload
    else:
        db.session.add(SiteSetting(key=SETTING_KEY, value=payload))
    db.session.commit()
    return normalized


def visible(cfg, path="/", inline_edit=False):
    if inline_edit:
        return bool(cfg)
    if not cfg or not cfg.get("enabled"):
        return False
    if not (cfg.get("image") or "").strip():
        return False
    if (path or "").startswith("/admin"):
        return False
    return promo_shown_on_path(cfg.get("show_pages"), path)
