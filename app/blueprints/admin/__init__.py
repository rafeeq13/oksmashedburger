"""Admin / Store management (SRS §4.16). Role-scoped: super_admin & franchise
owners can switch stores; a store_manager is pinned to their own store. Here a
location manages its OWN menu (availability + prices) and its OWN integrations."""
import csv
import io
import os
import re
import secrets
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from collections import Counter

from flask import Blueprint, render_template, request, redirect, flash, abort, Response, current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.auth import current_user, roles_required
from app.helpers import active_stores, get_current_store
from app.models.store import Store, StoreIntegration, StoreHours, StoreDeliveryZone
from app.models.menu import Product, StoreMenuItem, ProductVariant, ProductAddon, Category
from app.models.order import Order, OrderItem
from app.models.promo import Coupon, GiftCard, COUPON_KINDS
from app.models.user import User, Role
from app.models.site import SiteSetting, FEATURES, FEATURE_KEYS, features_from
from app.models.page import (
    PageSection, HOME_SECTIONS, SECTION_THEMES, home_sections_ordered, resolved_defaults,
    spec_for, is_custom_key, next_custom_key, PAGE_CONTENT, page_content_defaults,
    BuilderPage, unique_page_slug, slugify, DYNAMIC_SECTION_KEYS,
)
from app.models.favorite import Favorite
from app.models.address import UserAddress
from app.models.delivery import Driver
from app.services.orders import TRACK_STAGES, STAGE_META, advance, set_status

bp = Blueprint("admin", __name__)

ADMIN_ROLES = ("super_admin", "franchise_owner", "store_manager")

# Per-provider config fields shown on the Integrations page.
PROVIDERS = [
    {"key": "stripe", "name": "Stripe", "icon": "credit-card", "desc": "Online card payments",
     "fields": [{"key": "account_id", "label": "Account ID"}, {"key": "publishable_key", "label": "Publishable key"}, {"key": "secret_key", "label": "Secret key", "secret": True}]},
    {"key": "square", "name": "Square POS", "icon": "cash-register", "desc": "In-store payments & reconciliation",
     "fields": [{"key": "location_id", "label": "Location ID"}, {"key": "access_token", "label": "Access token", "secret": True}]},
    {"key": "uber_direct", "name": "Uber Direct", "icon": "car", "desc": "Third-party delivery dispatch",
     "fields": [{"key": "customer_id", "label": "Customer ID"}, {"key": "client_id", "label": "Client ID"}, {"key": "client_secret", "label": "Client secret", "secret": True}]},
    {"key": "google_maps", "name": "Google Maps", "icon": "map", "desc": "Geocoding, distance & ETA",
     "fields": [{"key": "api_key", "label": "API key", "secret": True}]},
    {"key": "twilio", "name": "Twilio", "icon": "comment-sms", "desc": "SMS notifications",
     "fields": [{"key": "account_sid", "label": "Account SID"}, {"key": "auth_token", "label": "Auth token", "secret": True}]},
    {"key": "sendgrid", "name": "SendGrid", "icon": "envelope", "desc": "Transactional & marketing email",
     "fields": [{"key": "api_key", "label": "API key", "secret": True}]},
]
_PROVIDER_KEYS = [p["key"] for p in PROVIDERS]


def _admin_store():
    slug = request.args.get("store")
    if slug:
        s = Store.query.filter_by(slug=slug).first()
        if s:
            return s
    u = current_user()
    if u and u.store_id:
        return Store.query.get(u.store_id)
    return get_current_store()


def _can_switch():
    return current_user().store_id is None


def _qs(store):
    return f"?store={store.slug}" if (_can_switch() and store) else ""


def _shell(store):
    return {"admin_store": store, "can_switch": _can_switch(),
            "admin_stores": active_stores(), "qs": _qs(store)}


# ── Dashboard ────────────────────────────────────────────────────────────
def _pct_delta(cur, prev):
    if not prev:
        return None
    return round((cur - prev) / prev * 100)


PERIODS = {"today": 1, "7d": 7, "30d": 30, "all": None}
PERIOD_LABELS = {"today": "today", "7d": "last 7 days", "30d": "last 30 days", "all": "all time"}


@bp.get("/admin")
@roles_required(*ADMIN_ROLES)
def index():
    store = _admin_store()
    orders = (Order.query.filter_by(store_id=store.id).order_by(Order.created_at.desc()).all()
              if store else [])
    today = datetime.now(timezone.utc).date()
    paid = [o for o in orders if o.payment_status == "paid"]

    # Period window scopes KPIs / pipeline / top sellers / comparison; delta is
    # this period vs the immediately-preceding equal-length period.
    period = request.args.get("period", "all")
    plen = PERIODS.get(period)
    if plen:
        start = today - timedelta(days=plen - 1)
        prev_start = start - timedelta(days=plen)
        window = [o for o in orders if o.created_at.date() >= start]
        prevw = [o for o in orders if prev_start <= o.created_at.date() < start]
    else:
        start, window, prevw = None, orders, []

    w_paid = [o for o in window if o.payment_status == "paid"]
    revenue = sum(float(o.total) for o in w_paid)
    prev_rev = sum(float(o.total) for o in prevw if o.payment_status == "paid")
    active = [o for o in orders if o.status not in ("completed", "cancelled")]

    kpis = {
        "revenue": revenue, "rev_delta": _pct_delta(revenue, prev_rev),
        "orders_ct": len(window), "orders_delta": _pct_delta(len(window), len(prevw)),
        "active": len(active), "aov": (revenue / len(w_paid)) if w_paid else 0.0,
        "completed": sum(1 for o in window if o.status == "completed"),
        "total": len(orders), "period": period, "period_label": PERIOD_LABELS.get(period, "all time"),
    }

    # 7-day revenue + order-count trend (fixed window, oldest → newest)
    series, max_rev = [], 0.0
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        d_rev = sum(float(o.total) for o in paid if o.created_at.date() == d)
        d_cnt = sum(1 for o in orders if o.created_at.date() == d)
        series.append({"label": d.strftime("%a"), "date": d.strftime("%b %d"),
                       "revenue": d_rev, "count": d_cnt})
        max_rev = max(max_rev, d_rev)
    for s in series:
        s["pct"] = round(s["revenue"] / max_rev * 100) if max_rev else 0
    week_rev = sum(s["revenue"] for s in series)

    # Status pipeline + top sellers (scoped to the selected period)
    counts = Counter(o.status for o in window)
    status_rows = [{"status": st, "label": STAGE_META.get(st, {}).get("label", st),
                    "icon": STAGE_META.get(st, {}).get("icon", "circle"), "count": counts.get(st, 0)}
                   for st in TRACK_STAGES + ["cancelled"]]

    agg = {}
    for o in window:
        for it in o.items:
            e = agg.setdefault(it.name, {"name": it.name, "qty": 0, "revenue": 0.0})
            e["qty"] += it.qty
            e["revenue"] += float(it.line_total)
    top_items = sorted(agg.values(), key=lambda x: x["qty"], reverse=True)[:6]

    # Multi-location comparison (only when the user can switch stores)
    store_perf = []
    if _can_switch():
        for s in active_stores():
            so = Order.query.filter_by(store_id=s.id).all()
            if start:
                so = [o for o in so if o.created_at.date() >= start]
            store_perf.append({
                "store": s, "orders": len(so),
                "revenue": sum(float(o.total) for o in so if o.payment_status == "paid"),
                "active": sum(1 for o in so if o.status not in ("completed", "cancelled")),
            })

    sold_out = sum(1 for mi in store.menu_items if not mi.is_available) if store else 0
    unpaid = sum(1 for o in active if o.payment_status != "paid")

    return render_template(
        "admin/index.html", kpis=kpis, series=series, week_rev=week_rev,
        status_rows=status_rows, top_items=top_items, recent=orders[:8],
        store_perf=store_perf, sold_out=sold_out, unpaid=unpaid,
        now_label=datetime.now(timezone.utc).strftime("%A, %b %d"), **_shell(store))


@bp.post("/admin/store/status")
@roles_required(*ADMIN_ROLES)
def store_status():
    """Open/close THIS store for immediate orders and/or scheduled ordering.
    Available to any admin role for their own store (managers open/close daily)."""
    store = _admin_store()
    if not store:
        abort(404)
    field = request.form.get("field")
    if field == "orders":
        store.accepting_orders = not store.accepting_orders
        msg = "now open for orders" if store.accepting_orders else "closed for new (ASAP) orders"
    elif field == "scheduled":
        store.accepting_scheduled = not store.accepting_scheduled
        msg = "scheduled ordering enabled" if store.accepting_scheduled else "scheduled ordering disabled"
    else:
        abort(400)
    db.session.commit()
    flash(f"{store.name}: {msg}.", "success")
    return redirect(request.form.get("next") or ("/admin" + _qs(store)))


# ── Opening hours (per location) ─────────────────────────────────────────
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@bp.get("/admin/hours")
@roles_required(*ADMIN_ROLES)
def hours():
    store = _admin_store()
    existing = {h.day_of_week: h for h in store.hours} if store else {}
    rows = []
    for d in range(7):
        h = existing.get(d)
        rows.append({"day": d, "label": _DAYS[d],
                     "open": (h.open_time if h and h.open_time else "11:00"),
                     "close": (h.close_time if h and h.close_time else "23:00"),
                     "closed": bool(h.is_closed) if h else False})
    return render_template("admin/hours.html", rows=rows, **_shell(store))


@bp.post("/admin/hours")
@roles_required(*ADMIN_ROLES)
def hours_save():
    store = _admin_store()
    if not store:
        abort(404)
    existing = {h.day_of_week: h for h in store.hours}
    for d in range(7):
        h = existing.get(d)
        if not h:
            h = StoreHours(store=store, day_of_week=d)
            db.session.add(h)
        h.is_closed = bool(request.form.get(f"closed_{d}"))
        h.open_time = (request.form.get(f"open_{d}") or "11:00")
        h.close_time = (request.form.get(f"close_{d}") or "23:00")
    db.session.commit()
    flash(f"{store.name} opening hours updated.", "success")
    if (request.form.get("next") or "").startswith("/admin/settings"):
        return redirect("/admin/settings" + _qs(store) + "#hours")
    return redirect("/admin/hours" + _qs(store))


# ── Store settings (order types, min order, delivery zones) ──────────────
@bp.get("/admin/settings")
@roles_required(*ADMIN_ROLES)
def settings():
    store = _admin_store()
    zones = list(store.delivery_zones) if store else []
    existing = {h.day_of_week: h for h in store.hours} if store else {}
    hour_rows = []
    for d in range(7):
        h = existing.get(d)
        hour_rows.append({"day": d, "label": _DAYS[d],
                          "open": (h.open_time if h and h.open_time else "11:00"),
                          "close": (h.close_time if h and h.close_time else "23:00"),
                          "closed": bool(h.is_closed) if h else False})
    return render_template("admin/settings.html", s=store, zones=zones, hour_rows=hour_rows, **_shell(store))


@bp.post("/admin/settings")
@roles_required(*ADMIN_ROLES)
def settings_save():
    store = _admin_store()
    if not store:
        abort(404)
    store.accepts_delivery = bool(request.form.get("accepts_delivery"))
    store.accepts_pickup = bool(request.form.get("accepts_pickup"))
    try:
        store.min_order_amount = Decimal(request.form.get("min_order_amount") or str(store.min_order_amount))
    except InvalidOperation:
        pass
    try:
        store.tax_rate = Decimal(request.form.get("tax_rate") or str(store.tax_rate))
    except InvalidOperation:
        pass
    store.delivery_radius_miles = request.form.get("delivery_radius_miles", type=float) or store.delivery_radius_miles
    store.avg_prep_minutes = request.form.get("avg_prep_minutes", type=int) or store.avg_prep_minutes
    store.currency = request.form.get("currency", "").strip().upper() or store.currency
    # Tips
    store.tips_enabled = bool(request.form.get("tips_enabled"))
    presets = []
    for raw in (request.form.get("tip_presets", "") or "").replace(" ", "").split(","):
        try:
            p = int(round(float(raw)))
            if 0 < p <= 100 and p not in presets:
                presets.append(p)
        except (ValueError, TypeError):
            continue
    store.tip_presets = presets[:4] or [15, 18, 20]
    db.session.commit()
    flash(f"{store.name} settings saved.", "success")
    return redirect("/admin/settings" + _qs(store) + "#general")


def _zone_from_form(z, form):
    z.name = form.get("name", "").strip() or z.name or "Zone"
    z.zip_codes = _csv_list(form.get("zip_codes"))
    z.color = form.get("color", "").strip() or z.color or "#E0A200"
    z.radius_miles = form.get("radius_miles", type=float) or z.radius_miles or 3.0
    z.est_minutes = form.get("est_minutes", type=int) or z.est_minutes or 30
    try:
        z.delivery_fee = Decimal(form.get("delivery_fee") or str(z.delivery_fee or "2.99"))
    except InvalidOperation:
        pass
    try:
        z.min_order = Decimal(form.get("min_order") or str(z.min_order or "0"))
    except InvalidOperation:
        pass


@bp.post("/admin/settings/zones")
@roles_required(*ADMIN_ROLES)
def zone_add():
    store = _admin_store()
    if not store:
        abort(404)
    z = StoreDeliveryZone(store=store, is_active=True)
    _zone_from_form(z, request.form)
    db.session.add(z)
    db.session.commit()
    flash(f"Delivery zone “{z.name}” added.", "success")
    return redirect("/admin/settings" + _qs(store) + "#zones")


@bp.post("/admin/settings/zones/<int:zid>/edit")
@roles_required(*ADMIN_ROLES)
def zone_edit(zid):
    store = _admin_store()
    z = StoreDeliveryZone.query.get_or_404(zid)
    if store and z.store_id != store.id:
        abort(403)
    _zone_from_form(z, request.form)
    db.session.commit()
    flash("Delivery zone updated.", "success")
    return redirect("/admin/settings" + _qs(store) + "#zones")


@bp.post("/admin/settings/zones/<int:zid>/toggle")
@roles_required(*ADMIN_ROLES)
def zone_toggle(zid):
    store = _admin_store()
    z = StoreDeliveryZone.query.get_or_404(zid)
    if store and z.store_id != store.id:
        abort(403)
    z.is_active = not z.is_active
    db.session.commit()
    return redirect("/admin/settings" + _qs(store) + "#zones")


@bp.post("/admin/settings/zones/<int:zid>/delete")
@roles_required(*ADMIN_ROLES)
def zone_delete(zid):
    store = _admin_store()
    z = StoreDeliveryZone.query.get_or_404(zid)
    if store and z.store_id != store.id:
        abort(403)
    db.session.delete(z)
    db.session.commit()
    flash("Delivery zone removed.", "success")
    return redirect("/admin/settings" + _qs(store) + "#zones")


# ── Site images (brand-wide storefront section pictures) ─────────────────
# (group title, [(setting key, label), …]). Templates read `site.get(key)` and
# fall back to their built-in default when a key isn't set.
# (group title, [(setting key, label, where it shows, required size, ratio), …])
# The size is the box the site actually paints the picture into, doubled for a
# retina screen — measured in a browser, not guessed, so a designer can build
# to it before uploading rather than after seeing it cropped.
SITE_IMAGE_SLOTS = [
    ("Brand", [
        ("brand_logo", "Logo",
         "Everywhere — site header, mobile menu, footer, the sign-in pages, the "
         "gift-card artwork and the admin panel. A transparent PNG or SVG works best.",
         "480×640", "any, it is scaled to fit"),
        ("brand_favicon", "Browser tab icon",
         "The little icon in the browser tab and in a bookmark. Square, and it has "
         "to stay readable at 16 pixels — usually just the mark, not the full logo.",
         "512×512", "1:1"),
        ("brand_app_icon", "Home-screen icon",
         "Used when someone saves the site to a phone home screen. Square, and it "
         "gets rounded corners, so keep clear space around the edge.",
         "512×512", "1:1"),
    ]),
    ("Home hero carousel", [
        ("hero_%d_img" % i, "Slide %d" % i,
         "Home page — hero carousel, slide %d. The same picture is a wide band on "
         "a desktop and a tall one on a phone, so keep the subject in the middle "
         "third." % i, "2560×1440", "16:9") for i in range(1, 11)]),
    ("Home sections", [
        ("catering_img", "Catering banner",
         "Home page — the full-width catering band. Also used as the band on the About page.",
         "2400×1200", "2:1"),
        ("about_img", "About / team photo",
         "Home page — the story band. Also the photo and the video poster on the About page.",
         "1200×1500", "4:5 portrait"),
        ("franchise_img", "Franchise banner",
         "Home page — the yellow franchise band, right-hand photo.",
         "1600×1500", "16:15"),
    ]),
    ("Home — Instagram grid", [
        ("ig_%d_img" % i, "Instagram tile %d" % i,
         "Home page and About page — Instagram grid, tile %d. Square, nothing is cropped." % i,
         "800×800", "1:1") for i in range(1, 9)]),
    ("About page — Instagram grid", [
        ("about_ig_%d_img" % i, "About tile %d" % i,
         "About page — Instagram grid, tile %d. Leave it empty and this tile "
         "shows whatever the home page's tile %d shows." % (i, i),
         "800×800", "1:1") for i in range(1, 9)]),
    ("About page — Instagram reel links", [
        ("about_ig_%d_reel" % i, "About reel link %d" % i,
         "About page — tapping tile %d opens this link. Empty falls back to the "
         "home page's link for the same tile. A URL, not an image." % i,
         "", "") for i in range(1, 9)]),
    ("Page banners", [
        ("catering_hero_img", "Catering page hero", "Catering page — the banner across the top.", "2560×1200", "21:10"),
        ("careers_hero_img", "Careers page hero", "Join Our Team page — the banner across the top.", "2560×1200", "21:10"),
        ("about_hero_img", "About page hero", "About page — the banner across the top.", "2560×1200", "21:10"),
        ("contact_hero_img", "Contact page hero", "Contact page — the banner across the top.", "2560×1200", "21:10"),
        ("deals_hero_img", "Deals page banner", "Deals page — the banner across the top.", "2560×1200", "21:10"),
        ("giftcards_hero_img", "Gift cards page banner", "Gift cards page — the banner across the top.", "2560×1200", "21:10"),
        ("rewards_hero_img", "Rewards page banner", "Rewards page — the banner across the top. This is the tallest banner on the site.", "2560×1440", "16:9"),
        ("faq_hero_img", "FAQ / help hero", "Help centre page — the banner across the top.", "2560×1200", "21:10"),
    ]),
    ("About page photos", [
        ("about_card1_img", "Story card 1 photo", "About page — the first of the two story cards.", "1200×900", "4:3"),
        ("about_card2_img", "Story card 2 photo", "About page — the second story card.", "1200×900", "4:3"),
        ("about_table_img", "“Meet us at the table” photo", "About page — the photo beside “Meet us at the table”.", "1200×900", "4:3"),
        ("about_crew_img", "Team photo", "About page — the tilted team photo near the bottom.", "1200×1200", "1:1"),
        ("about_kitchen_img", "Kitchen photo",
         "About page — the “inside our kitchen” photo beside the story text. "
         "Until you set it, it borrows the home page’s story photo.",
         "1200×1500", "4:5 portrait"),
        ("about_video_poster", "Video poster",
         "About page — the still shown before the video plays. Until you set it, "
         "it borrows the home page’s story photo.",
         "1920×1080", "16:9"),
        ("about_band_img", "Full-width band photo",
         "About page — the full-width photo band lower down. Until you set it, it "
         "borrows the home page’s catering banner.",
         "2400×1200", "2:1"),
    ]),
    ("Other page photos", [
        ("rewards_refer_img", "Rewards — refer a friend", "Rewards page — the “refer a friend” card.", "1200×900", "4:3"),
        ("giftcards_corporate_img", "Gift cards — corporate gifting", "Gift cards page — the corporate gifting card.", "1000×625", "16:10"),
        ("faq_support_img", "FAQ — support photo", "Help centre page — the photo beside the support text.", "1200×900", "4:3"),
        ("tracking_map_img", "Order tracking — map picture", "Order tracking page — the picture standing in for the live map.", "1600×1000", "16:10"),
    ]),
    ("Instagram reels (paste a reel link per tile)", [
        ("ig_%d_reel" % i, "Reel link for tile %d" % i,
         "Home page — tapping Instagram tile %d opens this link. A URL, not an image." % i,
         "", "") for i in range(1, 9)]),
    ("Videos (self-hosted)", [
        ("about_video", "About page video (MP4/WEBM, or paste a YouTube/Vimeo link)",
         "About page — plays in place of the photo. Upload MP4/WEBM or paste a YouTube/Vimeo link.",
         "1920×1080", "16:9"),
    ]),
    ("Sign in & sign up pages", [
        ("login_img", "Sign-in panel photo", "Sign-in page — the photo panel beside the form. Hidden on phones.", "1024×1400", "3:4 portrait"),
        ("register_img", "Sign-up panel photo", "Sign-up page — a very tall photo panel. Hidden on phones.", "1024×2200", "1:2 tall"),
        ("forgot_img", "Forgot-password panel photo", "Forgot-password page — the photo panel. Hidden on phones.", "1024×1400", "3:4 portrait"),
    ]),
]


@bp.get("/admin/site-images")
@roles_required(*ADMIN_ROLES)
def site_images():
    store = _admin_store()
    current = {s.key: s.value for s in SiteSetting.query.all()}
    return render_template("admin/site_images.html", groups=SITE_IMAGE_SLOTS,
                           current=current, **_shell(store))


@bp.post("/admin/site-images")
@roles_required(*ADMIN_ROLES)
def site_images_save():
    store = _admin_store()
    for _title, slots in SITE_IMAGE_SLOTS:
        for slot in slots:
            key = slot[0]
            _exts = VIDEO_EXTS if key.endswith("_video") else IMAGE_EXTS
            uploaded = _save_image(request.files.get(key + "_file"),
                                   "site-" + key.replace("_", "-"), _exts)
            val = uploaded or request.form.get(key, "").strip()
            setting = SiteSetting.query.filter_by(key=key).first()
            if val:
                if setting:
                    setting.value = val
                else:
                    db.session.add(SiteSetting(key=key, value=val))
            elif setting:
                db.session.delete(setting)   # cleared → revert to the built-in default
    db.session.commit()
    flash("Site images updated.", "success")
    return redirect("/admin/site-images" + _qs(store))


# ── Features: switch whole areas of the storefront off ───────────────────
@bp.get("/admin/features")
@roles_required(*ADMIN_ROLES)
def features_page():
    store = _admin_store()
    rows = {r.key: r.value for r in SiteSetting.query.all() if r.value}
    flags = features_from(rows)
    current = {k: flags[k.replace("feature_", "")] for k in FEATURE_KEYS}
    return render_template("admin/features.html", features_spec=FEATURES,
                           current=current, **_shell(store))


@bp.post("/admin/features")
@roles_required(*ADMIN_ROLES)
def features_save():
    store = _admin_store()
    for key in FEATURE_KEYS:
        want_on = bool(request.form.get(key))
        row = SiteSetting.query.filter_by(key=key).first()
        if want_on:
            # on is the default, so an "on" feature keeps no row at all
            if row:
                db.session.delete(row)
        elif row:
            row.value = "off"
        else:
            db.session.add(SiteSetting(key=key, value="off"))
    db.session.commit()
    flash("Features updated.", "success")
    return redirect("/admin/features" + _qs(store))


# ── Page builder (home page sections: order, visibility, text, theme) ────
@bp.get("/admin/page-builder")
@roles_required(*ADMIN_ROLES)
def page_builder():
    """Retired — the Visual editor does everything this screen did.

    This was a drag-to-reorder list with a show/hide checkbox. /admin/canvas
    reorders, shows/hides, edits each section's text AND restyles it, so two
    tabs were offering the same job with different amounts of it. The route
    stays as a redirect: bookmarks and any older link still land somewhere
    useful instead of on a 404.
    """
    return redirect("/admin/canvas" + _qs(_admin_store()))


def _apply_page_builder_form():
    """Persist the submitted order / visibility / text / theme onto the home
    section rows (does NOT commit — the caller commits)."""
    order = request.form.getlist("order")         # section keys in the new order
    rows = {s.key: s for s in PageSection.query.filter_by(page="home").all()}
    defaults = resolved_defaults(current_app.config.get("BRAND_NAME", ""))
    for idx, key in enumerate(order):
        row = rows.get(key)
        if not row:
            continue
        row.sort_order = idx
        row.enabled = bool(request.form.get("enabled_" + key))
        spec = spec_for(key)
        cfg = dict(row.config or {})
        for field, _label, _default in spec.get("fields", []):
            val = (request.form.get("f_%s_%s" % (key, field)) or "").strip()
            default_val = defaults.get(key, {}).get(field) or _default or ""
            # Store only genuine changes; a value equal to the default is dropped
            # so the section keeps using the built-in copy.
            if val and val != default_val:
                cfg[field] = val
            else:
                cfg.pop(field, None)
        if spec.get("theme"):
            theme = (request.form.get("theme_" + key) or "").strip()
            if theme and theme != "default":
                cfg["theme"] = theme
            else:
                cfg.pop("theme", None)
        row.config = cfg


@bp.post("/admin/page-builder")
@roles_required(*ADMIN_ROLES)
def page_builder_save():
    store = _admin_store()
    _apply_page_builder_form()
    db.session.commit()
    flash("Home page layout saved.", "success")
    return redirect("/admin/page-builder" + _qs(store))


@bp.post("/admin/page-builder/add")
@roles_required(*ADMIN_ROLES)
def page_builder_add():
    store = _admin_store()
    _apply_page_builder_form()                    # keep unsaved edits
    typ = (request.form.get("type") or "content").strip()
    label = {"banner": "Announcement bar", "image": "Image + text", "content": "Text block"}.get(typ, "Custom block")
    cfg = {"_type": typ} if typ != "content" else {}
    key = next_custom_key()
    if typ == "banner":                           # banners belong at the very top
        base = db.session.query(db.func.min(PageSection.sort_order)).filter_by(page="home").scalar() or 0
        order_val = base - 1
        cfg.setdefault("heading", "Free delivery on your first order")
    else:
        order_val = (db.session.query(db.func.max(PageSection.sort_order)).filter_by(page="home").scalar() or 0) + 1
    db.session.add(PageSection(page="home", key=key, label=label,
                               enabled=True, sort_order=order_val, config=cfg))
    db.session.commit()
    flash(label + " added.", "success")
    return redirect("/admin/page-builder" + _qs(store) + "#sec-" + key)


@bp.post("/admin/page-builder/<int:sid>/duplicate")
@roles_required(*ADMIN_ROLES)
def page_builder_duplicate(sid):
    store = _admin_store()
    row = PageSection.query.get_or_404(sid)
    if not is_custom_key(row.key):
        flash("Only custom sections can be duplicated.", "error")
        return redirect("/admin/page-builder" + _qs(store))
    _apply_page_builder_form()
    key = next_custom_key()
    db.session.add(PageSection(page="home", key=key, label=row.label, enabled=row.enabled,
                               sort_order=(row.sort_order or 0) + 1, config=dict(row.config or {})))
    db.session.commit()
    flash("Section duplicated.", "success")
    return redirect("/admin/page-builder" + _qs(store))


@bp.post("/admin/page-builder/<int:sid>/delete")
@roles_required(*ADMIN_ROLES)
def page_builder_delete(sid):
    store = _admin_store()
    row = PageSection.query.get_or_404(sid)
    if not is_custom_key(row.key):
        flash("Built-in sections can't be deleted, hide them with the toggle instead.", "error")
        return redirect("/admin/page-builder" + _qs(store))
    _apply_page_builder_form()                    # keep unsaved edits to other rows
    db.session.delete(row)
    db.session.commit()
    flash("Section removed.", "success")
    return redirect("/admin/page-builder" + _qs(store))


# ── Page content (headline copy for the other storefront pages) ──────────
@bp.get("/admin/page-content")
@roles_required(*ADMIN_ROLES)
def page_content():
    store = _admin_store()
    current = {s.key: s.value for s in SiteSetting.query.all() if s.value}
    defaults = page_content_defaults(current_app.config.get("BRAND_NAME", ""))
    # paths that can also be rebuilt from scratch in the drag-drop builder, so
    # each page block can offer "Redesign" next to "View"
    taken = {p.override_path for p in BuilderPage.query.all() if p.override_path}
    overridable = {o[0] for o in BUILDER_OVERRIDABLE if o[0] not in taken}
    return render_template("admin/page_content.html", pages=PAGE_CONTENT,
                           current=current, defaults=defaults,
                           overridable=overridable, **_shell(store))


@bp.post("/admin/page-content")
@roles_required(*ADMIN_ROLES)
def page_content_save():
    store = _admin_store()
    defaults = page_content_defaults(current_app.config.get("BRAND_NAME", ""))
    for p in PAGE_CONTENT:
        for field in p["fields"]:
            key = field[0]
            # Only touch what this form actually carried. The loop used to walk
            # every field in the registry and delete any it could not find in
            # the request, so a form covering one page would wipe the copy on
            # all the others — which is exactly what a per-page editor posts.
            if key not in request.form:
                continue
            val = (request.form.get(key) or "").strip()
            setting = SiteSetting.query.filter_by(key=key).first()
            if val and val != (defaults.get(key) or ""):
                if setting:
                    setting.value = val
                else:
                    db.session.add(SiteSetting(key=key, value=val))
            elif setting:
                db.session.delete(setting)        # cleared or == default → use default
    db.session.commit()
    flash("Page content saved.", "success")
    return redirect(request.form.get("next") or ("/admin/page-content" + _qs(store)))


# ── Visual canvas editor (drag/reorder + live restyle of home sections) ──
CANVAS_FONTS = [
    ("", "Default"),
    ("'Poppins',sans-serif", "Poppins (bold display)"),
    ("'Quicksand',sans-serif", "Quicksand (rounded)"),
    ("'Inter',sans-serif", "Inter (clean)"),
    ("Georgia,'Times New Roman',serif", "Georgia (serif)"),
    ("'Arial Black',Impact,sans-serif", "Arial Black (heavy)"),
    ("'Courier New',monospace", "Courier (mono)"),
]


@bp.get("/admin/canvas")
@roles_required(*ADMIN_ROLES)
def canvas():
    store = _admin_store()
    sections = home_sections_ordered()
    defaults = resolved_defaults(current_app.config.get("BRAND_NAME", ""))
    state = []
    for row in sections:
        spec = spec_for(row.key)
        fields = [{"key": f, "label": lbl, "default": (defaults.get(row.key, {}).get(f) or d or "")}
                  for f, lbl, d in spec.get("fields", [])]
        state.append({
            "key": row.key, "sid": row.id, "label": row.label,
            "enabled": bool(row.enabled), "custom": bool(spec.get("custom")),
            "config": row.config or {}, "fields": fields,
        })
    return render_template("admin/canvas.html", inner_pages=INNER_PAGES, state=state, fonts=CANVAS_FONTS, **_shell(store))


@bp.post("/admin/canvas/save")
@roles_required(*ADMIN_ROLES)
def canvas_save():
    items = (request.get_json(silent=True) or {}).get("sections", [])
    rows = {s.key: s for s in PageSection.query.filter_by(page="home").all()}
    for i, item in enumerate(items):
        row = rows.get(item.get("key"))
        if not row:
            continue
        row.sort_order = i
        row.enabled = bool(item.get("enabled", True))
        cfg = item.get("config")
        if isinstance(cfg, dict):
            row.config = cfg
    db.session.commit()
    return {"ok": True}


# ── GrapesJS drag-drop page builder (standalone pages at /p/<slug>) ───────
@bp.get("/admin/builder")
@roles_required(*ADMIN_ROLES)
def builder_list():
    store = _admin_store()
    pages = BuilderPage.query.order_by(BuilderPage.created_at.desc()).all()
    taken = {p.override_path for p in pages if p.override_path}
    overridable = [o for o in BUILDER_OVERRIDABLE if o[0] not in taken]
    return render_template("admin/builder_list.html", pages=pages,
                           overridable=overridable, **_shell(store))


def _tpl_section(inner, bg="#fff", pad="64px 20px", color="#141414"):
    return ('<section style="background:%s;color:%s;padding:%s"><div style="max-width:1100px;margin:0 auto">%s</div></section>'
            % (bg, color, pad, inner))


BUILDER_TEMPLATES = {
    "blank": ("Blank", ""),
    "landing": ("Landing page",
                _tpl_section('<div style="text-align:center;max-width:640px;margin:0 auto"><h1 style="font-family:Poppins,sans-serif;font-weight:800;font-size:48px;margin:0 0 16px;text-transform:uppercase">Big bold headline</h1><p style="font-size:18px;color:#ddd;margin:0 0 24px">Say what you offer in one clear line.</p><a href="/menu" style="display:inline-block;background:#FFC72C;color:#141414;font-weight:700;padding:14px 30px;border-radius:10px;text-decoration:none">Order now</a></div>', "#141414", "96px 20px", "#fff")
                + '<section data-dyn="best_sellers"></section>'
                + _tpl_section('<div style="text-align:center"><h2 style="font-family:Poppins,sans-serif;font-weight:800;font-size:32px;margin:0 0 8px">Ready to order?</h2><a href="/menu" style="display:inline-block;background:#141414;color:#fff;font-weight:700;padding:13px 30px;border-radius:10px;text-decoration:none;margin-top:12px">Get started</a></div>', "#FFC72C")),
    "about": ("About page",
              _tpl_section('<div style="text-align:center;max-width:640px;margin:0 auto"><h1 style="font-family:Poppins,sans-serif;font-weight:800;font-size:44px;margin:0 0 14px">About us</h1><p style="font-size:17px;color:#ddd">Our story, in a few honest words.</p></div>', "#141414", "80px 20px", "#fff")
              + _tpl_section('<div style="display:flex;gap:40px;align-items:center;flex-wrap:wrap"><img src="https://images.unsplash.com/photo-1552566626-52f8b828add9?w=700&h=500&fit=crop" style="flex:1;min-width:280px;max-width:520px;width:100%;border-radius:16px"><div style="flex:1;min-width:280px"><h2 style="font-family:Poppins,sans-serif;font-weight:800;font-size:30px;margin:0 0 14px">How it started</h2><p style="color:#666;line-height:1.6">Write your brand story here.</p></div></div>')),
    "contact": ("Contact page",
                _tpl_section('<div style="text-align:center;max-width:640px;margin:0 auto"><h1 style="font-family:Poppins,sans-serif;font-weight:800;font-size:44px;margin:0 0 14px">Get in touch</h1><p style="color:#ddd">We reply fast.</p></div>', "#141414", "72px 20px", "#fff")
                + _tpl_section('<form style="max-width:520px;margin:0 auto"><input name="name" placeholder="Your name" style="width:100%;padding:12px;margin:0 0 12px;border:1px solid #ddd;border-radius:8px"><input name="email" placeholder="Email" style="width:100%;padding:12px;margin:0 0 12px;border:1px solid #ddd;border-radius:8px"><textarea name="message" placeholder="Message" style="width:100%;padding:12px;margin:0 0 12px;border:1px solid #ddd;border-radius:8px;min-height:120px"></textarea><button style="background:#FFC72C;color:#141414;font-weight:700;padding:12px 28px;border:none;border-radius:8px;cursor:pointer">Send message</button></form>')),
    "pricing": ("Pricing page",
                _tpl_section('<div style="text-align:center;margin:0 0 36px"><h1 style="font-family:Poppins,sans-serif;font-weight:800;font-size:40px;margin:0">Simple pricing</h1></div><div style="display:flex;gap:24px;flex-wrap:wrap;justify-content:center">'
                            + "".join('<div style="flex:1;min-width:220px;max-width:300px;border:1px solid #eee;border-radius:16px;padding:28px;text-align:center"><h3 style="font-weight:700;font-size:20px;margin:0 0 8px">%s</h3><div style="font-family:Poppins,sans-serif;font-weight:800;font-size:40px;margin:0 0 16px">$%s</div><a href="#" style="display:inline-block;background:#141414;color:#fff;font-weight:700;padding:11px 24px;border-radius:8px;text-decoration:none">Choose</a></div>' % (n, p) for n, p in [("Basic", "9"), ("Popular", "19"), ("Pro", "29")])
                            + '</div>')),
}


# Existing storefront pages that can be taken over and rebuilt in the builder.
# (path, label, template to preload the real design from)
BUILDER_OVERRIDABLE = [
    ("/about", "About", "website/about.html"),
    ("/contact", "Contact", "website/contact.html"),
    ("/catering", "Catering", "website/catering.html"),
    ("/careers", "Careers", "website/careers.html"),
    ("/faq", "FAQ", "website/faq.html"),
    ("/news", "News", "website/news.html"),
    ("/deals", "Deals", "website/deals.html"),
    ("/rewards", "Rewards", "website/rewards.html"),
    ("/gift-cards", "Gift cards", "website/gift-cards.html"),
]
# /menu and /locations are deliberately NOT here: their content is the live menu
# and store list, so a rebuilt copy would freeze that data into static HTML.
# Their headings are editable in Page Content instead.


def _extract_page_content(template_name):
    """Render a storefront page and pull out just its <main> body so it can be
    pre-loaded into the builder as an editable copy of the real design."""
    full = render_template(template_name)
    m = re.search(r"<main\b[^>]*>(.*)</main>", full, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


@bp.post("/admin/builder/new")
@roles_required(*ADMIN_ROLES)
def builder_new():
    store = _admin_store()
    title = (request.form.get("title") or "Untitled page").strip() or "Untitled page"
    tpl = request.form.get("template") or "blank"
    html = BUILDER_TEMPLATES.get(tpl, ("", ""))[1]
    override = (request.form.get("override") or "").strip()
    ov = next((o for o in BUILDER_OVERRIDABLE if o[0] == override), None)
    opath = None
    if ov:
        if BuilderPage.query.filter_by(override_path=ov[0]).first():
            flash("A builder page already replaces %s — edit or delete that one." % ov[0], "error")
            return redirect("/admin/builder" + _qs(store))
        opath = ov[0]
        title = ov[1] + " page"
        try:
            content = _extract_page_content(ov[2])
            if content:
                html = content
        except Exception:
            pass
    page = BuilderPage(title=title, slug=unique_page_slug(title), html=html, css="",
                       gjs={}, published=True, override_path=opath)
    db.session.add(page)
    db.session.commit()
    return redirect("/admin/builder/%d" % page.id + _qs(store))


@bp.post("/admin/builder/<int:pid>/duplicate")
@roles_required(*ADMIN_ROLES)
def builder_duplicate(pid):
    store = _admin_store()
    src = BuilderPage.query.get_or_404(pid)
    dup = BuilderPage(title=src.title + " (copy)", slug=unique_page_slug(src.title + " copy"),
                      html=src.html, css=src.css, gjs=src.gjs, published=False,
                      meta_title=src.meta_title, meta_description=src.meta_description, head_code=src.head_code)
    db.session.add(dup)
    db.session.commit()
    flash("Page duplicated as a draft.", "success")
    return redirect("/admin/builder/%d" % dup.id + _qs(store))


# Sections that pull live DB data (rendered as non-editable "live blocks"); the
# rest are pre-loaded as FULLY-EDITABLE HTML so every card/text/button/link in
# them can be edited, restyled and dragged in the visual builder.
_HOME_LIVE_KEYS = {"hero", "explore_menu", "best_sellers", "locations"}


@bp.post("/admin/builder/new-home")
@roles_required(*ADMIN_ROLES)
def builder_new_home():
    """Create (or open) a drag-drop HOME page pre-loaded with the real home:
    data-driven sections as live blocks, everything else as editable HTML."""
    store = _admin_store()
    existing = BuilderPage.query.filter_by(is_home=True).first()
    if existing:
        return redirect("/admin/builder/%d" % existing.id + _qs(store))
    parts = []
    for k in DYNAMIC_SECTION_KEYS:
        if k in _HOME_LIVE_KEYS:
            parts.append('<section data-dyn="%s"></section>' % k)
        else:
            try:
                parts.append(render_template("website/sections/%s.html" % k, cfg={}))
            except Exception:
                parts.append('<section data-dyn="%s"></section>' % k)
    page = BuilderPage(title="Home page", slug=unique_page_slug("home"),
                       html="".join(parts), css="", gjs={}, published=True, is_home=True)
    db.session.add(page)
    db.session.commit()
    flash("Home page loaded into the builder — every text, card and button is now editable.", "success")
    return redirect("/admin/builder/%d" % page.id + _qs(store))


@bp.get("/admin/builder/<int:pid>")
@roles_required(*ADMIN_ROLES)
def builder_edit(pid):
    store = _admin_store()
    page = BuilderPage.query.get_or_404(pid)
    # Starting image library for the asset manager: uploaded files + site images.
    from app.models.site import SITE_IMAGE_DEFAULTS
    assets = list(dict.fromkeys(SITE_IMAGE_DEFAULTS.values()))
    updir = os.path.join(current_app.static_folder, "img", "uploads")
    if os.path.isdir(updir):
        for fn in sorted(os.listdir(updir)):
            if os.path.splitext(fn)[1].lower() in IMAGE_EXTS:
                assets.append("/static/img/uploads/" + fn)
    return render_template("admin/builder_edit.html", page=page,
                           dyn_keys=DYNAMIC_SECTION_KEYS, assets=assets, **_shell(store))


def _wire_forms(html):
    """Point any admin-dropped <form> that has no action attribute at the generic
    /form-submit handler. Uses a whitespace-anchored match so `data-action=` and
    other `*action=` attributes are not treated as an existing action."""
    def repl(m):
        tag = m.group(0)
        if re.search(r"\saction\s*=", tag):
            return tag
        return tag[:-1] + ' action="/form-submit" method="post">'
    return re.sub(r"<form[^>]*>", repl, html or "")


@bp.get("/admin/builder/<int:pid>/code")
@roles_required(*ADMIN_ROLES)
def builder_code(pid):
    store = _admin_store()
    page = BuilderPage.query.get_or_404(pid)
    return render_template("admin/builder_code.html", page=page, **_shell(store))


@bp.post("/admin/builder/<int:pid>/code")
@roles_required(*ADMIN_ROLES)
def builder_code_save(pid):
    store = _admin_store()
    page = BuilderPage.query.get_or_404(pid)
    page.html = _wire_forms(request.form.get("html", "") or "")
    page.css = request.form.get("css", "") or ""
    page.head_code = (request.form.get("head_code") or "").strip() or None
    page.gjs = {}          # written by hand → let the visual editor re-import from HTML
    db.session.commit()
    flash("Page code saved.", "success")
    return redirect("/admin/builder/%d/code" % page.id + _qs(store))


@bp.post("/admin/builder/<int:pid>/store")
@roles_required(*ADMIN_ROLES)
def builder_store(pid):
    page = BuilderPage.query.get_or_404(pid)
    data = request.get_json(silent=True) or {}
    page.html = _wire_forms(data.get("html", "") or "")
    page.css = data.get("css", "") or ""
    if isinstance(data.get("gjs"), dict):
        page.gjs = data["gjs"]
    db.session.commit()
    return {"ok": True}


@bp.post("/admin/builder/upload")
@roles_required(*ADMIN_ROLES)
def builder_upload():
    """Image upload target for the GrapesJS asset manager (returns {data:[{src}]})."""
    urls = []
    for f in request.files.getlist("files"):
        u = _save_image(f, "page-" + secrets.token_hex(6))
        if u:
            urls.append({"src": u})
    return {"data": urls}


@bp.post("/admin/builder/<int:pid>/meta")
@roles_required(*ADMIN_ROLES)
def builder_meta(pid):
    store = _admin_store()
    page = BuilderPage.query.get_or_404(pid)
    page.title = (request.form.get("title") or page.title).strip() or page.title
    new_slug = slugify(request.form.get("slug") or page.slug)
    if new_slug != page.slug:
        if BuilderPage.query.filter_by(slug=new_slug).first():
            flash("The URL slug “%s” is already taken, keeping the current one." % new_slug, "error")
        else:
            page.slug = new_slug
    page.published = bool(request.form.get("published"))
    page.show_in_nav = bool(request.form.get("show_in_nav"))
    # Only overwrite a field the submitted form actually carries. `head_code` is
    # owned by BOTH this form and the full code editor, so a settings POST that
    # does not include it (a partial/scripted save) must not wipe it.
    for field in ("meta_title", "meta_description", "head_code"):
        if field in request.form:
            setattr(page, field, (request.form.get(field) or "").strip() or None)
    if request.form.get("detach_override"):
        page.override_path = None       # restore the original storefront page
    make_home = bool(request.form.get("is_home"))
    if make_home and not page.is_home:
        BuilderPage.query.filter_by(is_home=True).update({"is_home": False})
        page.is_home = True
    elif not make_home:
        page.is_home = False
    db.session.commit()
    flash("Page settings saved.", "success")
    return redirect("/admin/builder/%d" % page.id + _qs(store))


@bp.post("/admin/builder/<int:pid>/delete")
@roles_required(*ADMIN_ROLES)
def builder_delete(pid):
    store = _admin_store()
    page = BuilderPage.query.get_or_404(pid)
    db.session.delete(page)
    db.session.commit()
    flash("Page deleted.", "success")
    return redirect("/admin/builder" + _qs(store))


# ── Menu management ──────────────────────────────────────────────────────
@bp.get("/admin/menu")
@roles_required(*ADMIN_ROLES)
def menu():
    store = _admin_store()
    existing = {mi.product_id: mi for mi in store.menu_items} if store else {}
    rows = []
    for p in Product.query.order_by(Product.category_id, Product.sort_order).all():
        mi = existing.get(p.id)
        rows.append({
            "product": p,
            "listed": mi.is_listed if mi else False,
            "available": mi.is_available if mi else True,
            "price": float(mi.price_override) if (mi and mi.price_override is not None) else float(p.base_price),
        })
    return render_template("admin/menu.html", rows=rows,
                           categories=Category.query.order_by(Category.sort_order).all(), **_shell(store))


@bp.post("/admin/menu/<int:pid>")
@roles_required(*ADMIN_ROLES)
def menu_save(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    mi = StoreMenuItem.query.filter_by(store_id=store.id, product_id=pid).first()
    if not mi:
        mi = StoreMenuItem(store_id=store.id, product_id=pid)
        db.session.add(mi)
    mi.is_listed = bool(request.form.get("listed"))
    mi.is_available = bool(request.form.get("available"))
    price = request.form.get("price", type=float)
    mi.price_override = round(price, 2) if (price is not None and abs(price - float(product.base_price)) > 0.001) else None
    db.session.commit()
    flash(f"{product.name} updated.", "success")
    return redirect("/admin/menu" + _qs(store))


# ── Menu-item modifiers: sizes/variants (single-select) + add-ons (multi) ─
# Modifiers live on the brand catalog (Product), so they apply everywhere the
# product is listed. They render on the item page and flow into cart/checkout.
@bp.get("/admin/menu/<int:pid>/modifiers")
@roles_required(*ADMIN_ROLES)
def product_modifiers(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    return render_template("admin/product_modifiers.html", product=product, **_shell(store))


@bp.post("/admin/menu/<int:pid>/variants")
@roles_required(*ADMIN_ROLES)
def variant_add(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Enter a size/variant name.", "error")
        return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))
    try:
        delta = Decimal(request.form.get("price_delta") or "0")
    except InvalidOperation:
        delta = Decimal("0")
    make_default = bool(request.form.get("is_default")) or not product.variants
    if make_default:
        for v in product.variants:
            v.is_default = False
    db.session.add(ProductVariant(product=product, name=name, price_delta=delta, is_default=make_default))
    db.session.commit()
    flash(f"Added size “{name}”.", "success")
    return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))


@bp.post("/admin/menu/variants/<int:vid>/default")
@roles_required(*ADMIN_ROLES)
def variant_default(vid):
    store = _admin_store()
    v = ProductVariant.query.get_or_404(vid)
    for sib in v.product.variants:
        sib.is_default = (sib.id == v.id)
    db.session.commit()
    return redirect(f"/admin/menu/{v.product_id}/modifiers" + _qs(store))


@bp.post("/admin/menu/variants/<int:vid>/delete")
@roles_required(*ADMIN_ROLES)
def variant_delete(vid):
    store = _admin_store()
    v = ProductVariant.query.get_or_404(vid)
    pid, was_default = v.product_id, v.is_default
    db.session.delete(v)
    db.session.flush()
    # Keep exactly one default if any remain.
    remaining = ProductVariant.query.filter_by(product_id=pid).all()
    if was_default and remaining and not any(r.is_default for r in remaining):
        remaining[0].is_default = True
    db.session.commit()
    flash("Size removed.", "success")
    return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))


@bp.post("/admin/menu/<int:pid>/addons")
@roles_required(*ADMIN_ROLES)
def addon_add(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Enter an add-on name.", "error")
        return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))
    try:
        price = Decimal(request.form.get("price") or "0")
    except InvalidOperation:
        price = Decimal("0")
    db.session.add(ProductAddon(product=product, name=name, price=price))
    db.session.commit()
    flash(f"Added add-on “{name}”.", "success")
    return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))


@bp.post("/admin/menu/addons/<int:aid>/delete")
@roles_required(*ADMIN_ROLES)
def addon_delete(aid):
    store = _admin_store()
    a = ProductAddon.query.get_or_404(aid)
    pid = a.product_id
    db.session.delete(a)
    db.session.commit()
    flash("Add-on removed.", "success")
    return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))


# ── Catalog: create/edit products & categories (brand-wide) ──────────────
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTS = (".mp4", ".webm")


def _csv_list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _unique_slug(name, model=Product):
    base = _slugify(name)
    slug, i = base, 2
    while model.query.filter_by(slug=slug).first():
        slug, i = f"{base}-{i}", i + 1
    return slug


def _save_image(file, slug, exts=IMAGE_EXTS):
    """Save an uploaded file under /static/img/uploads and return its URL.

    `exts` lets a caller widen the whitelist, e.g. the About page video slot
    accepts MP4/WEBM. Everything else still only takes images.
    """
    if not file or not getattr(file, "filename", ""):
        return None
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in exts:
        flash("Unsupported file type — allowed: %s." % ", ".join(e.lstrip(".").upper() for e in exts), "error")
        return None
    updir = os.path.join(current_app.static_folder, "img", "uploads")
    os.makedirs(updir, exist_ok=True)
    fname = secure_filename(f"{slug}{ext}")
    file.save(os.path.join(updir, fname))
    return f"/static/img/uploads/{fname}"


def _apply_product_form(p, form, files):
    p.name = form.get("name", "").strip() or p.name
    cat = Category.query.get(form.get("category_id", type=int)) if form.get("category_id") else None
    if cat:
        p.category = cat
    try:
        p.base_price = Decimal(form.get("base_price") or str(p.base_price))
    except InvalidOperation:
        pass
    p.description = form.get("description", "").strip()
    p.calories = form.get("calories", type=int)
    p.allergens = _csv_list(form.get("allergens"))
    p.tags = _csv_list(form.get("tags"))
    p.is_vegan = bool(form.get("is_vegan"))
    p.sort_order = form.get("sort_order", type=int) or 0
    uploaded = _save_image(files.get("image_file"), p.slug)
    url = form.get("image_url", "").strip()
    if uploaded:
        p.image_url = uploaded
    elif url:
        p.image_url = url


@bp.post("/admin/catalog/products")
@roles_required(*ADMIN_ROLES)
def product_add():
    store = _admin_store()
    name = request.form.get("name", "").strip()
    if not name or not request.form.get("category_id"):
        flash("Item name and category are required.", "error")
        return redirect("/admin/menu" + _qs(store))
    p = Product(slug=_unique_slug(name), name=name, base_price=Decimal("0"),
                category=Category.query.get(request.form.get("category_id", type=int)))
    _apply_product_form(p, request.form, request.files)
    db.session.add(p)
    db.session.flush()
    for s in Store.query.all():  # auto-list the new item on every location
        db.session.add(StoreMenuItem(store_id=s.id, product_id=p.id, is_listed=True, is_available=True))
    db.session.commit()
    flash(f"“{p.name}” added and listed on all locations. Add sizes/add-ons below.", "success")
    return redirect(f"/admin/menu/{p.id}/edit" + _qs(store))


@bp.get("/admin/menu/<int:pid>/edit")
@roles_required(*ADMIN_ROLES)
def product_edit(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    return render_template("admin/product_edit.html", product=product,
                           categories=Category.query.order_by(Category.sort_order).all(), **_shell(store))


@bp.post("/admin/menu/<int:pid>/edit")
@roles_required(*ADMIN_ROLES)
def product_update(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    _apply_product_form(product, request.form, request.files)
    product.is_active = bool(request.form.get("is_active"))
    db.session.commit()
    flash(f"“{product.name}” updated.", "success")
    return redirect(f"/admin/menu/{pid}/edit" + _qs(store))


@bp.post("/admin/menu/<int:pid>/delete")
@roles_required(*ADMIN_ROLES)
def product_delete(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    if OrderItem.query.filter_by(product_id=pid).count():
        product.is_active = False
        db.session.commit()
        flash(f"“{product.name}” has order history — archived instead of deleted.", "success")
    else:
        name = product.name
        db.session.delete(product)  # cascades variants / add-ons / store listings
        db.session.commit()
        flash(f"“{name}” deleted from the catalog.", "success")
    return redirect("/admin/menu" + _qs(store))


@bp.post("/admin/catalog/categories")
@roles_required(*ADMIN_ROLES)
def category_add():
    store = _admin_store()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Category name is required.", "error")
        return redirect("/admin/menu" + _qs(store))
    db.session.add(Category(slug=_unique_slug(name, Category), name=name,
                            icon=request.form.get("icon", "").strip() or "utensils",
                            description=request.form.get("description", "").strip() or None,
                            image_url=request.form.get("image_url", "").strip() or None,
                            sort_order=request.form.get("sort_order", type=int) or 0))
    db.session.commit()
    flash(f"Category “{name}” added.", "success")
    return redirect("/admin/menu" + _qs(store))


@bp.post("/admin/catalog/categories/<int:cid>/edit")
@roles_required(*ADMIN_ROLES)
def category_edit(cid):
    store = _admin_store()
    c = Category.query.get_or_404(cid)
    c.name = request.form.get("name", "").strip() or c.name
    c.icon = request.form.get("icon", "").strip() or c.icon
    if "description" in request.form:
        c.description = request.form.get("description", "").strip() or None
    c.image_url = request.form.get("image_url", "").strip() or None
    if request.form.get("sort_order"):
        c.sort_order = request.form.get("sort_order", type=int)
    db.session.commit()
    flash("Category updated.", "success")
    return redirect("/admin/menu" + _qs(store))


@bp.post("/admin/catalog/categories/<int:cid>/delete")
@roles_required(*ADMIN_ROLES)
def category_delete(cid):
    store = _admin_store()
    c = Category.query.get_or_404(cid)
    if c.products:
        flash("Move or remove this category's items before deleting it.", "error")
    else:
        db.session.delete(c)
        db.session.commit()
        flash("Category deleted.", "success")
    return redirect("/admin/menu" + _qs(store))


# ── Integrations (each location's own keys) ──────────────────────────────
@bp.get("/admin/integrations")
@roles_required(*ADMIN_ROLES)
def integrations():
    store = _admin_store()
    existing = {i.provider: i for i in store.integrations} if store else {}
    providers = []
    for p in PROVIDERS:
        integ = existing.get(p["key"])
        providers.append({**p, "enabled": integ.enabled if integ else False,
                          "config": (integ.config or {}) if integ else {}})
    return render_template("admin/integrations.html", providers=providers, **_shell(store))


@bp.post("/admin/integrations/<provider>")
@roles_required(*ADMIN_ROLES)
def integrations_save(provider):
    store = _admin_store()
    if provider not in _PROVIDER_KEYS:
        abort(404)
    integ = StoreIntegration.query.filter_by(store_id=store.id, provider=provider).first()
    if not integ:
        integ = StoreIntegration(store_id=store.id, provider=provider, config={})
        db.session.add(integ)
    integ.enabled = bool(request.form.get("enabled"))
    cfg = dict(integ.config or {})
    for key, val in request.form.items():
        if key.startswith("cfg_"):
            cfg[key[4:]] = val.strip()
    integ.config = cfg  # reassign so SQLAlchemy detects the JSON change
    db.session.commit()
    flash(f"{provider.replace('_', ' ').title()} settings saved.", "success")
    return redirect("/admin/integrations" + _qs(store) + f"#{provider}")


# ── Locations / stores ───────────────────────────────────────────────────
LOCATION_ROLES = ("super_admin", "franchise_owner")  # who may add/toggle stores


def _can_manage_locations():
    return current_user().role.name in LOCATION_ROLES


def _slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "store"


@bp.get("/admin/locations")
@roles_required(*ADMIN_ROLES)
def locations():
    store = _admin_store()
    rows = []
    for s in Store.query.order_by(Store.name).all():
        orders = Order.query.filter_by(store_id=s.id).all()
        rows.append({
            "store": s,
            "integrations": sum(1 for i in s.integrations if i.enabled),
            "menu": sum(1 for mi in s.menu_items if mi.is_listed),
            "orders": len(orders),
            "revenue": sum(float(o.total) for o in orders if o.payment_status == "paid"),
        })
    return render_template("admin/locations.html", rows=rows,
                           can_manage=_can_manage_locations(), **_shell(store))


@bp.post("/admin/locations")
@roles_required(*ADMIN_ROLES)
def location_add():
    if not _can_manage_locations():
        abort(403)
    store = _admin_store()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Store name is required.", "error")
        return redirect("/admin/locations" + _qs(store))
    slug = _slugify(request.form.get("slug", "").strip() or name)
    if Store.query.filter_by(slug=slug).first():
        flash("A location with that name already exists.", "error")
        return redirect("/admin/locations" + _qs(store))
    try:
        tax = Decimal(request.form.get("tax_rate") or "0.08")
    except InvalidOperation:
        tax = Decimal("0.08")

    s = Store(
        slug=slug, name=name,
        address_line=request.form.get("address_line", "").strip(),
        city=request.form.get("city", "").strip() or "Philadelphia",
        state=request.form.get("state", "").strip() or "PA",
        zip_code=request.form.get("zip_code", "").strip(),
        phone=request.form.get("phone", "").strip(),
        email=request.form.get("email", "").strip() or f"{slug}@oksmashedburger.com",
        tax_rate=tax, avg_prep_minutes=int(request.form.get("avg_prep_minutes") or 15))
    db.session.add(s)
    db.session.flush()

    # Sensible defaults so the new location is immediately operational.
    for d in range(7):
        db.session.add(StoreHours(store=s, day_of_week=d, open_time="11:00", close_time="23:00"))
    db.session.add(StoreDeliveryZone(store=s, name="Local",
                                     zip_codes=[s.zip_code] if s.zip_code else [],
                                     delivery_fee=Decimal("2.99")))
    for p in Product.query.filter_by(is_active=True).all():
        db.session.add(StoreMenuItem(store=s, product=p, is_listed=True, is_available=True))
    db.session.commit()
    flash(f"Location “{name}” created with the full menu. Set up its integrations next.", "success")
    return redirect(f"/admin/integrations?store={slug}")


@bp.post("/admin/locations/<int:sid>/toggle")
@roles_required(*ADMIN_ROLES)
def location_toggle(sid):
    if not _can_manage_locations():
        abort(403)
    store = _admin_store()
    s = Store.query.get_or_404(sid)
    s.is_active = not s.is_active
    db.session.commit()
    flash(f"{s.name} {'activated' if s.is_active else 'deactivated'}.", "success")
    return redirect("/admin/locations" + _qs(store))


@bp.post("/admin/locations/<int:sid>/edit")
@roles_required(*ADMIN_ROLES)
def location_edit(sid):
    if not _can_manage_locations():
        abort(403)
    s = Store.query.get_or_404(sid)
    s.name = request.form.get("name", "").strip() or s.name
    s.address_line = request.form.get("address_line", "").strip()
    s.city = request.form.get("city", "").strip() or s.city
    s.state = request.form.get("state", "").strip() or s.state
    s.zip_code = request.form.get("zip_code", "").strip()
    s.phone = request.form.get("phone", "").strip()
    s.email = request.form.get("email", "").strip() or s.email
    try:
        s.tax_rate = Decimal(request.form.get("tax_rate") or str(s.tax_rate))
    except InvalidOperation:
        pass
    s.avg_prep_minutes = int(request.form.get("avg_prep_minutes") or s.avg_prep_minutes)
    db.session.commit()
    flash(f"{s.name} updated.", "success")
    return redirect("/admin/locations" + _qs(_admin_store()))


@bp.post("/admin/locations/<int:sid>/delete")
@roles_required(*ADMIN_ROLES)
def location_delete(sid):
    if not _can_manage_locations():
        abort(403)
    s = Store.query.get_or_404(sid)
    if Order.query.filter_by(store_id=s.id).count():
        flash("This location has orders — deactivate it instead of deleting.", "error")
        return redirect("/admin/locations" + _qs(_admin_store()))
    # Detach any staff / drivers pinned here, then delete (cascades menu/zones/hours/integrations).
    User.query.filter_by(store_id=s.id).update({"store_id": None})
    Driver.query.filter_by(store_id=s.id).update({"store_id": None})
    name = s.name
    db.session.delete(s)
    db.session.commit()
    flash(f"Location “{name}” deleted.", "success")
    return redirect("/admin/locations")


@bp.get("/admin/orders/<number>/receipt.pdf")
@roles_required(*ADMIN_ROLES)
def order_receipt(number):
    from app.services.receipts import build_receipt_pdf
    order = _scoped_order(number)
    return Response(build_receipt_pdf(order), mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=receipt-{order.number}.pdf"})


# ── Orders ───────────────────────────────────────────────────────────────
def _parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _date_window(args):
    """Resolve a (range-preset OR custom from/to) into (rng, since, until) dates."""
    today = datetime.now(timezone.utc).date()
    rng = args.get("range", "")
    since, until = _parse_date(args.get("from")), _parse_date(args.get("to"))
    if rng == "today":
        since = until = today
    elif rng == "7d":
        since, until = today - timedelta(days=6), today
    elif rng == "30d":
        since, until = today - timedelta(days=29), today
    elif rng == "all":
        since = until = None
    return rng, since, until


def _orders_filtered(store, status, since=None, until=None):
    if not store:
        return []
    q = Order.query.filter_by(store_id=store.id)
    if status == "active":
        q = q.filter(Order.status.notin_(["completed", "cancelled"]))
    elif status in TRACK_STAGES or status == "cancelled":
        q = q.filter_by(status=status)
    if since:
        q = q.filter(Order.created_at >= datetime.combine(since, datetime.min.time()))
    if until:
        q = q.filter(Order.created_at < datetime.combine(until + timedelta(days=1), datetime.min.time()))
    return q.order_by(Order.created_at.desc()).all()


@bp.get("/admin/orders")
@roles_required(*ADMIN_ROLES)
def orders():
    store = _admin_store()
    status = request.args.get("status")
    rng, since, until = _date_window(request.args)
    return render_template("admin/orders.html", orders=_orders_filtered(store, status, since, until),
                           status=status, stages=TRACK_STAGES, rng=rng,
                           date_from=request.args.get("from", ""), date_to=request.args.get("to", ""),
                           **_shell(store))


@bp.get("/admin/orders/export.csv")
@roles_required(*ADMIN_ROLES)
def orders_export():
    store = _admin_store()
    _, since, until = _date_window(request.args)
    rows = _orders_filtered(store, request.args.get("status"), since, until)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Order", "Date", "Customer", "Email", "Phone", "Type", "Items",
                "Status", "Payment", "Subtotal", "Discount", "Tax", "Delivery", "Tip", "Total"])
    for o in rows:
        w.writerow([o.number, o.created_at.strftime("%Y-%m-%d %H:%M"), o.customer_name or "",
                    o.customer_email or "", o.customer_phone or "", o.order_type, o.item_count,
                    o.status, o.payment_status, f"{float(o.subtotal):.2f}", f"{float(o.discount or 0):.2f}",
                    f"{float(o.tax):.2f}", f"{float(o.delivery_fee or 0):.2f}", f"{float(o.tip or 0):.2f}",
                    f"{float(o.total):.2f}"])
    fname = f"orders-{store.slug if store else 'all'}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


def _scoped_order(number):
    """Fetch an order, enforcing that a pinned manager only sees their store."""
    order = Order.query.filter_by(number=number).first_or_404()
    if not _can_switch() and order.store_id != current_user().store_id:
        abort(403)
    return order


@bp.get("/admin/orders/<number>")
@roles_required(*ADMIN_ROLES)
def order_detail(number):
    order = _scoped_order(number)
    store = Store.query.get(order.store_id)
    return render_template("admin/order_detail.html", order=order,
                           stages=TRACK_STAGES, stage_meta=STAGE_META, **_shell(store))


@bp.post("/admin/orders/<number>/status")
@roles_required(*ADMIN_ROLES)
def order_status(number):
    order = _scoped_order(number)
    action = request.form.get("action")
    if action == "advance":
        advance(order)                       # also fires the customer notification
        flash(f"{order.number} advanced to {order.status.replace('_', ' ')}.", "success")
    elif action == "cancel":
        set_status(order, "cancelled")
        flash(f"{order.number} cancelled.", "success")
    elif action == "mark_paid":
        order.payment_status = "paid"
        db.session.commit()
        flash(f"{order.number} marked paid.", "success")
    else:
        st = request.form.get("status")
        if st in TRACK_STAGES or st == "cancelled":
            set_status(order, st)
            flash(f"{order.number} set to {st.replace('_', ' ')}.", "success")
    return redirect(f"/admin/orders/{number}" + _qs(_admin_store()))


# ── Customers (brand-wide) ───────────────────────────────────────────────
def _customer_rows(search=""):
    users = User.query.join(Role).filter(Role.name == "customer").all()
    search = (search or "").strip().lower()
    rows = []
    for u in users:
        if search and search not in (u.full_name or "").lower() and search not in (u.email or "").lower():
            continue
        uo = Order.query.filter_by(user_id=u.id).all()
        spend = sum(float(o.total) for o in uo if o.payment_status == "paid")
        rows.append({"user": u, "orders": len(uo), "spend": spend,
                     "points": u.loyalty_points,
                     "last": max((o.created_at for o in uo), default=None)})
    rows.sort(key=lambda r: r["spend"], reverse=True)
    return rows


@bp.get("/admin/customers")
@roles_required(*ADMIN_ROLES)
def customers():
    store = _admin_store()
    q = request.args.get("q", "")
    return render_template("admin/customers.html", rows=_customer_rows(q), q=q, **_shell(store))


@bp.get("/admin/customers/export.csv")
@roles_required(*ADMIN_ROLES)
def customers_export():
    store = _admin_store()
    rows = _customer_rows(request.args.get("q", ""))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Email", "Phone", "Orders", "Total spend", "Loyalty points", "Last order", "Joined"])
    for r in rows:
        u = r["user"]
        w.writerow([u.full_name, u.email, u.phone or "", r["orders"], f"{r['spend']:.2f}",
                    r["points"], r["last"].strftime("%Y-%m-%d") if r["last"] else "",
                    u.created_at.strftime("%Y-%m-%d") if u.created_at else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=customers.csv"})


@bp.get("/admin/customers/<int:uid>")
@roles_required(*ADMIN_ROLES)
def customer_detail(uid):
    store = _admin_store()
    u = User.query.get_or_404(uid)
    orders = Order.query.filter_by(user_id=u.id).order_by(Order.created_at.desc()).all()
    paid = [o for o in orders if o.payment_status == "paid"]
    spend = sum(float(o.total) for o in paid)
    stats = {"orders": len(orders), "spend": spend, "aov": (spend / len(paid)) if paid else 0.0}
    favs = [f.product for f in Favorite.query.filter_by(user_id=u.id).all() if f.product]
    addrs = UserAddress.query.filter_by(user_id=u.id).order_by(UserAddress.is_default.desc()).all()
    return render_template("admin/customer_detail.html", u=u, orders=orders, stats=stats,
                           favs=favs, addrs=addrs, **_shell(store))


# ── Staff management ─────────────────────────────────────────────────────
STAFF_ROLES = ["franchise_owner", "store_manager", "kitchen_staff", "cashier", "driver"]


def _assignable_roles():
    """super_admin / franchise_owner may assign any staff role; a pinned
    store_manager may only add line staff to their own store."""
    if current_user().role.name in ("super_admin", "franchise_owner"):
        return STAFF_ROLES
    return ["kitchen_staff", "cashier", "driver"]


@bp.get("/admin/staff")
@roles_required(*ADMIN_ROLES)
def staff():
    store = _admin_store()
    q = User.query.join(Role).filter(Role.name.in_(STAFF_ROLES))
    if not _can_switch():
        q = q.filter(User.store_id == current_user().store_id)
    members = q.order_by(User.is_active.desc(), User.first_name).all()
    return render_template("admin/staff.html", members=members,
                           roles=_assignable_roles(), **_shell(store))


@bp.post("/admin/staff")
@roles_required(*ADMIN_ROLES)
def staff_add():
    store = _admin_store()
    email = request.form.get("email", "").strip().lower()
    role_name = request.form.get("role", "")
    if role_name not in _assignable_roles():
        flash("You're not allowed to assign that role.", "error")
        return redirect("/admin/staff" + _qs(store))
    if not email or "@" not in email or User.query.filter_by(email=email).first():
        flash("Enter a unique, valid email address.", "error")
        return redirect("/admin/staff" + _qs(store))

    # Store assignment: pinned managers use their own store; switchers may choose.
    target_store_id = current_user().store_id or (store.id if store else None)
    if _can_switch():
        chosen = Store.query.filter_by(slug=request.form.get("store", "")).first()
        target_store_id = chosen.id if chosen else (store.id if store else None)

    member = User(email=email, first_name=request.form.get("first_name", "").strip(),
                  last_name=request.form.get("last_name", "").strip(),
                  role=Role.query.filter_by(name=role_name).first(),
                  store_id=target_store_id, email_verified=True)
    member.set_password(request.form.get("password", "").strip() or "changeme123")
    db.session.add(member)
    db.session.commit()
    flash(f"Added {member.full_name or email} as {role_name.replace('_', ' ')}.", "success")
    return redirect("/admin/staff" + _qs(store))


@bp.post("/admin/staff/<int:sid>/toggle")
@roles_required(*ADMIN_ROLES)
def staff_toggle(sid):
    store = _admin_store()
    member = User.query.get_or_404(sid)
    if member.id == current_user().id:
        flash("You can't deactivate your own account.", "error")
    elif member.role.name == "super_admin":
        flash("Super admin accounts can't be changed here.", "error")
    elif not _can_switch() and member.store_id != current_user().store_id:
        abort(403)
    else:
        member.is_active = not member.is_active
        db.session.commit()
        flash(f"{member.full_name} {'reactivated' if member.is_active else 'deactivated'}.", "success")
    return redirect("/admin/staff" + _qs(store))


# ── Coupons / promotions (brand-wide) ────────────────────────────────────
@bp.get("/admin/coupons")
@roles_required(*ADMIN_ROLES)
def coupons():
    store = _admin_store()
    return render_template("admin/coupons.html", coupons=Coupon.query.order_by(Coupon.created_at.desc()).all(),
                           kinds=COUPON_KINDS, **_shell(store))


@bp.post("/admin/coupons")
@roles_required(*ADMIN_ROLES)
def coupons_create():
    store = _admin_store()
    code = request.form.get("code", "").strip().upper()
    kind = request.form.get("kind", "percent")
    if not code or kind not in COUPON_KINDS:
        flash("Enter a code and a valid type.", "error")
    elif Coupon.query.filter_by(code=code).first():
        flash("That code already exists.", "error")
    else:
        img = _save_image(request.files.get("image_file"), "deal-" + code.lower()) \
            or request.form.get("image_url", "").strip()
        db.session.add(Coupon(
            code=code, kind=kind,
            value=request.form.get("value", type=float) or 0,
            min_order=request.form.get("min_order", type=float) or 0,
            requires_code=bool(request.form.get("requires_code")),
            description=request.form.get("description", "").strip(),
            image_url=img or None, active=True))
        db.session.commit()
        flash(f"Coupon {code} created.", "success")
    return redirect("/admin/coupons" + _qs(store))


@bp.post("/admin/coupons/<int:cid>/edit")
@roles_required(*ADMIN_ROLES)
def coupons_edit(cid):
    store = _admin_store()
    c = Coupon.query.get_or_404(cid)
    if request.form.get("value") not in (None, ""):
        c.value = request.form.get("value", type=float) or 0
    if request.form.get("min_order") not in (None, ""):
        c.min_order = request.form.get("min_order", type=float) or 0
    if "description" in request.form:
        c.description = request.form.get("description", "").strip() or c.description
    # an upload wins over a pasted link; clearing the link box removes the photo
    uploaded = _save_image(request.files.get("image_file"), "deal-" + c.code.lower())
    if uploaded:
        c.image_url = uploaded
    elif "image_url" in request.form:
        c.image_url = request.form.get("image_url", "").strip() or None
    # checkboxes only post when checked, so this form controls them explicitly
    c.requires_code = bool(request.form.get("requires_code"))
    c.active = bool(request.form.get("active"))
    db.session.commit()
    flash(f"Coupon {c.code} updated.", "success")
    return redirect("/admin/coupons" + _qs(store))


@bp.post("/admin/coupons/<int:cid>/toggle")
@roles_required(*ADMIN_ROLES)
def coupons_toggle(cid):
    store = _admin_store()
    c = Coupon.query.get_or_404(cid)
    c.active = not c.active
    db.session.commit()
    return redirect("/admin/coupons" + _qs(store))


@bp.post("/admin/coupons/<int:cid>/delete")
@roles_required(*ADMIN_ROLES)
def coupons_delete(cid):
    store = _admin_store()
    c = Coupon.query.get_or_404(cid)
    code = c.code
    db.session.delete(c)
    db.session.commit()
    flash(f"Coupon {code} deleted.", "success")
    return redirect("/admin/coupons" + _qs(store))


# ── Gift cards (brand-wide) ──────────────────────────────────────────────
@bp.get("/admin/gift-cards")
@roles_required(*ADMIN_ROLES)
def gift_cards():
    store = _admin_store()
    cards = GiftCard.query.order_by(GiftCard.created_at.desc()).all()
    outstanding = sum(float(g.balance) for g in cards if g.active)
    issued = sum(float(g.initial_balance) for g in cards)
    return render_template("admin/gift_cards.html", cards=cards,
                           outstanding=outstanding, issued=issued, **_shell(store))


@bp.post("/admin/gift-cards")
@roles_required(*ADMIN_ROLES)
def gift_card_issue():
    store = _admin_store()
    try:
        amount = Decimal(request.form.get("amount") or "0")
    except InvalidOperation:
        amount = Decimal("0")
    if amount < 5 or amount > 1000:
        flash("Enter an amount between $5 and $1000.", "error")
        return redirect("/admin/gift-cards" + _qs(store))
    code = "OKGC-" + secrets.token_hex(3).upper()
    db.session.add(GiftCard(code=code, initial_balance=amount, balance=amount, active=True,
                            recipient_email=request.form.get("recipient", "").strip(),
                            sender_name=request.form.get("sender", "").strip() or "OK Smashed Burger",
                            message=request.form.get("message", "").strip()))
    db.session.commit()
    flash(f"Gift card {code} issued for ${amount:.2f}.", "success")
    return redirect("/admin/gift-cards" + _qs(store))


@bp.post("/admin/gift-cards/<int:gid>/toggle")
@roles_required(*ADMIN_ROLES)
def gift_card_toggle(gid):
    store = _admin_store()
    g = GiftCard.query.get_or_404(gid)
    g.active = not g.active
    db.session.commit()
    flash(f"Gift card {g.code} {'activated' if g.active else 'deactivated'}.", "success")
    return redirect("/admin/gift-cards" + _qs(store))


# ── Notifications log (this store's SMS/email sends) ─────────────────────
@bp.get("/admin/notifications")
@roles_required(*ADMIN_ROLES)
def notifications():
    from app.services.notifications import recent_for_store
    store = _admin_store()
    rows = recent_for_store(store.id) if store else []
    return render_template("admin/notifications.html", rows=rows, **_shell(store))


# ── Contact messages (brand-wide inbox) ──────────────────────────────────
@bp.get("/admin/messages")
@roles_required(*ADMIN_ROLES)
def messages():
    from app.models.contact import ContactMessage
    store = _admin_store()
    rows = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(100).all()
    return render_template("admin/messages.html", rows=rows, **_shell(store))


# ── Content lists ────────────────────────────────────────────────────────
# Hero slides, reviews, job openings, news, FAQ and catering packages used to
# be literal lists inside the templates. They are rows now, so the client owns
# them. Until a list is imported the site still renders the built-in defaults.
from app.models.content import (                                    # noqa: E402
    ContentItem, CONTENT_LISTS, LIST_BY_KIND, defaults_for, import_defaults,
)


def _content_kind(kind):
    spec = LIST_BY_KIND.get(kind)
    if not spec:
        abort(404)
    return spec


def _content_payload(spec):
    """Read this list's own fields off the submitted form.

    Number fields are coerced: a form always hands back strings, and templates
    compare these values numerically (`r.stars >= i+1`), which blows up on a str.
    """
    out = {}
    for key, _label, ftype in spec["fields"]:
        val = request.form.get(key, "").strip()
        if ftype == "number":
            try:
                val = int(val)
            except (TypeError, ValueError):
                val = 0
        out[key] = val
    return out


@bp.get("/admin/content")
@roles_required(*ADMIN_ROLES)
def content_lists():
    store = _admin_store()
    kind = request.args.get("kind") or CONTENT_LISTS[0]["kind"]
    spec = _content_kind(kind)
    rows = (ContentItem.query.filter_by(kind=kind)
            .order_by(ContentItem.sort_order, ContentItem.id).all())
    counts = {c["kind"]: ContentItem.query.filter_by(kind=c["kind"]).count()
              for c in CONTENT_LISTS}
    return render_template("admin/content_lists.html",
                           lists=CONTENT_LISTS, spec=spec, kind=kind, rows=rows,
                           counts=counts, defaults=defaults_for(kind),
                           **_shell(store))


@bp.post("/admin/content/<kind>/import")
@roles_required(*ADMIN_ROLES)
def content_import(kind):
    _content_kind(kind)
    n = import_defaults(kind)
    if n:
        flash("Imported %d items from the website — they are yours to edit now." % n, "success")
    else:
        flash("This list already has items.", "error")
    return redirect("/admin/content?kind=" + kind)


@bp.post("/admin/content/<kind>/add")
@roles_required(*ADMIN_ROLES)
def content_add(kind):
    spec = _content_kind(kind)
    last = (db.session.query(db.func.max(ContentItem.sort_order))
            .filter_by(kind=kind).scalar() or 0)
    db.session.add(ContentItem(kind=kind, sort_order=last + 1, is_active=True,
                               data=_content_payload(spec)))
    db.session.commit()
    flash("Added.", "success")
    return redirect("/admin/content?kind=" + kind)


@bp.post("/admin/content/<int:iid>/edit")
@roles_required(*ADMIN_ROLES)
def content_edit(iid):
    row = ContentItem.query.get_or_404(iid)
    spec = _content_kind(row.kind)
    row.data = _content_payload(spec)
    db.session.commit()
    flash("Saved.", "success")
    return redirect("/admin/content?kind=" + row.kind)


@bp.post("/admin/content/<int:iid>/toggle")
@roles_required(*ADMIN_ROLES)
def content_toggle(iid):
    row = ContentItem.query.get_or_404(iid)
    row.is_active = not row.is_active
    db.session.commit()
    flash("Shown on the website." if row.is_active else "Hidden from the website.", "success")
    return redirect("/admin/content?kind=" + row.kind)


@bp.post("/admin/content/<int:iid>/move")
@roles_required(*ADMIN_ROLES)
def content_move(iid):
    """Swap places with the neighbour above/below. Renumbering the whole list
    first keeps ordering stable even if rows ever shared a sort_order."""
    row = ContentItem.query.get_or_404(iid)
    up = request.form.get("dir") == "up"
    siblings = (ContentItem.query.filter_by(kind=row.kind)
                .order_by(ContentItem.sort_order, ContentItem.id).all())
    i = next((n for n, r in enumerate(siblings) if r.id == row.id), None)
    j = (i - 1) if up else (i + 1)
    if i is not None and 0 <= j < len(siblings):
        for n, r in enumerate(siblings):
            r.sort_order = n
        siblings[i].sort_order, siblings[j].sort_order = j, i
        db.session.commit()
    return redirect("/admin/content?kind=" + row.kind)


@bp.post("/admin/content/<int:iid>/delete")
@roles_required("super_admin", "franchise_owner")
def content_delete(iid):
    row = ContentItem.query.get_or_404(iid)
    kind = row.kind
    db.session.delete(row)
    db.session.commit()
    flash("Removed.", "success")
    return redirect("/admin/content?kind=" + kind)


# ── Newsletter subscribers ───────────────────────────────────────────────
# The footer form had no backend at all, so sign-ups went nowhere and there was
# nothing for the client to look at.
@bp.get("/admin/subscribers")
@roles_required(*ADMIN_ROLES)
def subscribers():
    from app.models.contact import Subscriber
    store = _admin_store()
    q = (request.args.get("q") or "").strip()
    query = Subscriber.query
    if q:
        query = query.filter(Subscriber.email.ilike("%" + q + "%"))
    rows = query.order_by(Subscriber.created_at.desc()).limit(500).all()
    return render_template("admin/subscribers.html", rows=rows, q=q,
                           total=Subscriber.query.count(),
                           active=Subscriber.query.filter_by(is_active=True).count(),
                           **_shell(store))


@bp.post("/admin/subscribers/<int:sid>/toggle")
@roles_required(*ADMIN_ROLES)
def subscriber_toggle(sid):
    from app.models.contact import Subscriber
    row = Subscriber.query.get_or_404(sid)
    row.is_active = not row.is_active
    db.session.commit()
    flash("Resubscribed." if row.is_active else "Unsubscribed.", "success")
    return redirect("/admin/subscribers")


@bp.post("/admin/subscribers/<int:sid>/delete")
@roles_required("super_admin", "franchise_owner")
def subscriber_delete(sid):
    from app.models.contact import Subscriber
    db.session.delete(Subscriber.query.get_or_404(sid))
    db.session.commit()
    flash("Removed from the list.", "success")
    return redirect("/admin/subscribers")


@bp.get("/admin/subscribers/export.csv")
@roles_required(*ADMIN_ROLES)
def subscribers_export():
    from app.models.contact import Subscriber
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "source", "status", "signed_up"])
    for s in Subscriber.query.order_by(Subscriber.created_at.desc()).all():
        w.writerow([s.email, s.source or "",
                    "active" if s.is_active else "unsubscribed",
                    s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=subscribers.csv"})


# ── Delivery drivers ─────────────────────────────────────────────────────
# Driver rows only ever came from the seed script; there was no way to add a
# rider, retire one, or take somebody offline without opening the database.
@bp.get("/admin/drivers")
@roles_required(*ADMIN_ROLES)
def drivers():
    from app.models.delivery import Delivery
    store = _admin_store()
    rows = (Driver.query.filter_by(store_id=store.id).order_by(Driver.name).all()
            if store else Driver.query.order_by(Driver.name).all())
    trips = {d.id: Delivery.query.filter_by(driver_id=d.id).count() for d in rows}
    linkable = User.query.join(Role).filter(Role.name == "driver").order_by(User.email).all()
    return render_template("admin/drivers.html", rows=rows, trips=trips,
                           linkable=linkable, **_shell(store))


@bp.post("/admin/drivers")
@roles_required(*ADMIN_ROLES)
def driver_add():
    store = _admin_store()
    name = request.form.get("name", "").strip()
    if not name:
        flash("A driver needs a name.", "error")
        return redirect("/admin/drivers" + _qs(store))
    db.session.add(Driver(
        name=name,
        phone=request.form.get("phone", "").strip(),
        vehicle=request.form.get("vehicle", "").strip(),
        store_id=store.id if store else None,
        user_id=request.form.get("user_id", type=int) or None,
        is_active=True, is_online=False))
    db.session.commit()
    flash(name + " added to the fleet.", "success")
    return redirect("/admin/drivers" + _qs(store))


@bp.post("/admin/drivers/<int:did>/edit")
@roles_required(*ADMIN_ROLES)
def driver_edit(did):
    d = Driver.query.get_or_404(did)
    d.name = request.form.get("name", "").strip() or d.name
    d.phone = request.form.get("phone", "").strip()
    d.vehicle = request.form.get("vehicle", "").strip()
    d.user_id = request.form.get("user_id", type=int) or None
    db.session.commit()
    flash("Driver updated.", "success")
    return redirect("/admin/drivers" + _qs(_admin_store()))


@bp.post("/admin/drivers/<int:did>/toggle")
@roles_required(*ADMIN_ROLES)
def driver_toggle(did):
    d = Driver.query.get_or_404(did)
    if request.form.get("field") == "is_online":
        d.is_online = not d.is_online
        msg = d.name + (" is online." if d.is_online else " is offline.")
    else:
        d.is_active = not d.is_active
        msg = d.name + (" reactivated." if d.is_active else " deactivated.")
    db.session.commit()
    flash(msg, "success")
    return redirect("/admin/drivers" + _qs(_admin_store()))


@bp.post("/admin/drivers/<int:did>/delete")
@roles_required("super_admin", "franchise_owner")
def driver_delete(did):
    from app.models.delivery import Delivery
    d = Driver.query.get_or_404(did)
    if Delivery.query.filter_by(driver_id=d.id).count():
        # never orphan delivery history — retire the driver instead
        d.is_active = False
        d.is_online = False
        db.session.commit()
        flash(d.name + " has deliveries on record, so they were deactivated instead of deleted.",
              "success")
    else:
        db.session.delete(d)
        db.session.commit()
        flash("Driver removed.", "success")
    return redirect("/admin/drivers" + _qs(_admin_store()))


# ── Customer reviews (moderation) ────────────────────────────────────────
# Public submissions land as `pending` and are invisible until approved here.
from app.models.review import Review, pending_count                 # noqa: E402


@bp.get("/admin/reviews")
@roles_required(*ADMIN_ROLES)
def reviews():
    store = _admin_store()
    status = request.args.get("status") or "pending"
    q = Review.query
    if status in ("pending", "approved", "rejected"):
        q = q.filter_by(status=status)
    rows = q.order_by(Review.created_at.desc()).limit(200).all()
    counts = {s: Review.query.filter_by(status=s).count()
              for s in ("pending", "approved", "rejected")}
    return render_template("admin/reviews.html", rows=rows, status=status,
                           counts=counts, **_shell(store))


def _moderate(rid, new_status):
    row = Review.query.get_or_404(rid)
    row.status = new_status
    row.moderated_at = datetime.now(timezone.utc)
    u = current_user()
    row.moderated_by_id = u.id if u else None
    db.session.commit()
    return row


@bp.post("/admin/reviews/<int:rid>/approve")
@roles_required(*ADMIN_ROLES)
def review_approve(rid):
    row = _moderate(rid, "approved")
    flash("Published — %s's review is live on the site." % row.display_name, "success")
    return redirect(request.form.get("next") or "/admin/reviews")


@bp.post("/admin/reviews/<int:rid>/reject")
@roles_required(*ADMIN_ROLES)
def review_reject(rid):
    _moderate(rid, "rejected")
    flash("Rejected — it stays hidden from the site.", "success")
    return redirect(request.form.get("next") or "/admin/reviews")


@bp.post("/admin/reviews/<int:rid>/delete")
@roles_required("super_admin", "franchise_owner")
def review_delete(rid):
    db.session.delete(Review.query.get_or_404(rid))
    db.session.commit()
    flash("Review deleted.", "success")
    return redirect(request.form.get("next") or "/admin/reviews")


# ── Theme (brand palette, type, shape) ───────────────────────────────────
# The palette lived only in premium.css, so a colour change meant editing a
# stylesheet. These are settings now, emitted as a :root{} block in the head.
from app.models.theme import (                                      # noqa: E402
    THEME_TOKENS, FONT_CHOICES, theme_values, theme_css,
)


@bp.get("/admin/theme")
@roles_required("super_admin", "franchise_owner")
def theme():
    store = _admin_store()
    return render_template("admin/theme.html",
                           tokens=THEME_TOKENS, fonts=FONT_CHOICES,
                           values=theme_values(), css=theme_css(),
                           **_shell(store))


@bp.post("/admin/theme")
@roles_required("super_admin", "franchise_owner")
def theme_save():
    changed = 0
    for key, _label, _prop, _kind, _default, _help in THEME_TOKENS:
        val = (request.form.get(key) or "").strip()
        row = SiteSetting.query.filter_by(key=key).first()
        # An empty box means "use the built-in value", so the row is removed
        # rather than stored blank — that keeps theme_css() free of noise.
        if not val:
            if row:
                db.session.delete(row)
                changed += 1
            continue
        if row:
            if row.value != val:
                row.value = val
                changed += 1
        else:
            db.session.add(SiteSetting(key=key, value=val))
            changed += 1
    db.session.commit()
    flash("Theme saved." if changed else "Nothing changed.", "success")
    return redirect("/admin/theme")


@bp.post("/admin/theme/reset")
@roles_required("super_admin", "franchise_owner")
def theme_reset():
    keys = [t[0] for t in THEME_TOKENS]
    n = SiteSetting.query.filter(SiteSetting.key.in_(keys)).delete(synchronize_session=False)
    db.session.commit()
    flash("Theme reset to the built-in design." if n else "Already on the built-in design.",
          "success")
    return redirect("/admin/theme")


# ── Page design (per-section styling for every inner page) ───────────────
# The Visual Editor only ever reached the home page. Every top-level section on
# the other nine pages is wrapped in the same .pb-sec shell now, so the same
# style vocabulary works there — this is the UI for it.
from app.models.page import INNER_PAGES, INNER_PAGE_BY_KEY, inner_sections  # noqa: E402

# key, label, input type — matches what pb_section_style() understands
DESIGN_FIELDS = [
    ("style_bg", "Section background", "color"),
    ("style_hcolor", "Heading colour", "color"),
    ("style_tcolor", "Text colour", "color"),
    ("style_align", "Text alignment", "align"),
    ("style_pt", "Padding top", "px"),
    ("style_pb", "Padding bottom", "px"),
    ("style_cardbg", "Card background", "color"),
    ("style_cardborder", "Card border", "color"),
    ("style_cardhead", "Card heading", "color"),
    ("style_cardtext", "Card text", "color"),
    ("style_cardradius", "Card radius", "px"),
    ("style_overlay", "Image overlay", "opacity"),
]


@bp.get("/admin/design")
@roles_required(*ADMIN_ROLES)
def design():
    store = _admin_store()
    page = request.args.get("page") or INNER_PAGES[0]["page"]
    spec = INNER_PAGE_BY_KEY.get(page)
    if not spec:
        abort(404)
    styled = {s["key"]: any(str(v).strip() for k, v in s["config"].items()
                            if k.startswith("style_"))
              for s in inner_sections(page)}
    # The words on this page live in the same screen as its design now — a
    # client editing the Contact page should not have to work out that the
    # heading is on one tab and the section colour on another.
    current = {r.key: r.value for r in SiteSetting.query.all() if r.value}
    defaults = page_content_defaults(current_app.config.get("BRAND_NAME", ""))
    text_groups = [g for g in PAGE_CONTENT if g.get("url") == spec["url"]]
    return render_template("admin/design.html",
                           pages=INNER_PAGES, page=page, spec=spec,
                           sections=inner_sections(page), fields=DESIGN_FIELDS,
                           styled=styled, text_groups=text_groups,
                           content_current=current, content_defaults=defaults,
                           **_shell(store))


@bp.post("/admin/design/<page>/<key>")
@roles_required(*ADMIN_ROLES)
def design_save(page, key):
    if page not in INNER_PAGE_BY_KEY:
        abort(404)
    row = PageSection.query.filter_by(page=page, key=key).first()
    if not row:
        label = next((s["label"] for s in INNER_PAGE_BY_KEY[page]["sections"]
                      if s["key"] == key), key)
        row = PageSection(page=page, key=key, label=label, enabled=True, sort_order=0)
        db.session.add(row)

    cfg = dict(row.config or {})
    for fkey, _label, _kind in DESIGN_FIELDS:
        val = (request.form.get(fkey) or "").strip()
        # blank clears the override rather than storing "" — keeps the inline
        # style attribute (and therefore the CSS) free of dead declarations
        if val:
            cfg[fkey] = val
        else:
            cfg.pop(fkey, None)
    row.config = cfg
    db.session.commit()
    flash("Saved.", "success")
    return redirect("/admin/design?page=" + page + "#s-" + key)


@bp.post("/admin/design/<page>/<key>/reset")
@roles_required(*ADMIN_ROLES)
def design_reset(page, key):
    row = PageSection.query.filter_by(page=page, key=key).first()
    if row:
        row.config = {k: v for k, v in (row.config or {}).items()
                      if not k.startswith("style_")}
        db.session.commit()
    flash("Section reset to the built-in design.", "success")
    return redirect("/admin/design?page=" + page + "#s-" + key)


@bp.post("/admin/design/<page>/reset-all")
@roles_required("super_admin", "franchise_owner")
def design_reset_page(page):
    if page not in INNER_PAGE_BY_KEY:
        abort(404)
    for row in PageSection.query.filter_by(page=page).all():
        row.config = {k: v for k, v in (row.config or {}).items()
                      if not k.startswith("style_")}
    db.session.commit()
    flash("Every section on this page is back to the built-in design.", "success")
    return redirect("/admin/design?page=" + page)


# ── Inline text editing ──────────────────────────────────────────────────
# An admin adds ?edit=1 to any storefront page and edits copy where it sits,
# instead of hunting for the matching field on the Page Content screen.
@bp.post("/admin/inline-save")
@roles_required(*ADMIN_ROLES)
def inline_save():
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    value = (data.get("value") or "").strip()

    # Only keys the Page Content registry knows about — this endpoint must not
    # become a way to write arbitrary settings rows.
    allowed = {f[0] for p in PAGE_CONTENT for f in p["fields"]}
    if key not in allowed:
        return {"ok": False, "error": "unknown field"}, 400

    row = SiteSetting.query.filter_by(key=key).first()
    if not value:
        # cleared -> fall back to the built-in copy rather than showing nothing
        if row:
            db.session.delete(row)
    elif row:
        row.value = value
    else:
        db.session.add(SiteSetting(key=key, value=value))
    db.session.commit()
    return {"ok": True, "key": key}
