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

from flask import Blueprint, render_template, request, redirect, flash, abort, Response, current_app, jsonify
from werkzeug.utils import secure_filename

from app.extensions import db
from app.auth import current_user, roles_required
from app.helpers import active_stores, get_current_store
from app.security import style_value_ok
from app.models.store import Store, StoreIntegration, StoreHours, StoreDeliveryZone
from app.models.menu import Product, StoreMenuItem, ProductVariant, ProductAddon, AddonLibrary, Category
from app.models.order import Order, OrderItem
from app.models.promo import Coupon, GiftCard, COUPON_KINDS
from app.models.user import User, Role
from app.models.site import SiteSetting, FEATURES, FEATURE_KEYS, features_from
from app.models.page import (
    PageSection, HOME_SECTIONS, SECTION_THEMES, home_sections_ordered, resolved_defaults,
    spec_for, is_custom_key, next_custom_key, PAGE_CONTENT, page_content_defaults,
    BuilderPage, unique_page_slug, slugify, DYNAMIC_SECTION_KEYS,
)
from app.models.email_templates import (
    EMAIL_TEMPLATE_GROUPS, EMAIL_LAYOUT, EMAIL_PLACEHOLDERS, email_template_defaults,
    email_layout_defaults, email_image_keys, preview_context, preview_rows,
    render as render_email, templates_for_admin,
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
    {"key": "smtp", "name": "SMTP email", "icon": "envelope", "desc": "Order updates, sign-up & marketing email",
     "fields": [
         {"key": "smtp_host", "label": "SMTP host"},
         {"key": "smtp_port", "label": "Port (587 STARTTLS, 465 SSL)"},
         {"key": "smtp_user", "label": "Username"},
         {"key": "smtp_password", "label": "Password", "secret": True},
         {"key": "from_email", "label": "From email"},
         {"key": "from_name", "label": "From name"},
         {"key": "reply_to", "label": "Reply-to (optional)"},
         {"key": "use_tls", "label": "Use STARTTLS (1=yes, 0=SSL on port 465)"},
     ]},
]
_PROVIDER_KEYS = [p["key"] for p in PROVIDERS]


# What the Visual editor's inspector can set. Anything outside this list that
# turns up in one of its saves belongs to another screen, so it is merged in
# rather than treated as the whole truth (see canvas_save).
CANVAS_STYLE_KEYS = {
    "style_bg", "style_accent", "style_overlay", "style_overlaycolor",
    "style_pt", "style_pb", "style_maxw", "style_align",
    "style_cardbg", "style_cardborder", "style_cardhead", "style_cardtext",
    "style_cardradius",
}


def _admin_store():
    """Which shop this admin screen is about.

    Someone pinned to one shop never leaves it. ?store= is how head office
    switches between shops | the same thing _can_switch() below allows only to
    a user with no shop of their own | so reading it first let a pinned manager
    open another shop's orders, exports and saved API keys just by editing the
    address bar. Nothing legitimate sends ?store= to a pinned user: _qs() gives
    them an empty query string.
    """
    u = current_user()
    if u and u.store_id:
        return Store.query.get(u.store_id)
    slug = request.args.get("store")
    if not slug and request.method == "POST":
        slug = (request.form.get("store") or "").strip() or None
    if slug:
        s = Store.query.filter_by(slug=slug).first()
        if s:
            return s
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
    """Opening hours live in Store settings, and only there.

    They used to be two screens editing the same seven rows | a tab inside
    Store settings and a page of their own in the sidebar | so it was never
    clear which one was the real one. This keeps old links and bookmarks
    working by sending them to the tab that owns it.
    """
    return redirect("/admin/settings" + _qs(_admin_store()) + "#hours")


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
    return redirect("/admin/settings" + _qs(store) + "#hours")


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
# retina screen | measured in a browser, not guessed, so a designer can build
# to it before uploading rather than after seeing it cropped.
SITE_IMAGE_SLOTS = [
    ("Brand", [
        ("brand_logo", "Logo",
         "Everywhere | site header, mobile menu, footer, the sign-in pages, the "
         "gift-card artwork and the admin panel. A transparent PNG or SVG works best.",
         "480×640", "any, it is scaled to fit"),
        ("brand_favicon", "Browser tab icon",
         "The little icon in the browser tab and in a bookmark. Square, and it has "
         "to stay readable at 16 pixels | usually just the mark, not the full logo.",
         "512×512", "1:1"),
        ("brand_app_icon", "Home-screen icon",
         "Used when someone saves the site to a phone home screen. Square, and it "
         "gets rounded corners, so keep clear space around the edge.",
         "512×512", "1:1"),
    ]),
    ("Home hero carousel", [
        ("hero_%d_img" % i, "Slide %d" % i,
         "Home page | hero carousel, slide %d. The same picture is a wide band on "
         "a desktop and a tall one on a phone, so keep the subject in the middle "
         "third." % i, "2560×1440", "16:9") for i in range(1, 11)]),
    ("Home sections", [
        ("catering_img", "Catering banner",
         "Home page | the full-width catering band. Also used as the band on the About page.",
         "2400×1200", "2:1"),
        ("about_img", "About / team photo",
         "Home page | the story band. Also the photo and the video poster on the About page.",
         "1200×1500", "4:5 portrait"),
        ("franchise_img", "Franchise banner",
         "Home page | the yellow franchise band, right-hand photo.",
         "1600×1500", "16:15"),
    ]),
    ("Home | Instagram grid", [
        ("ig_%d_img" % i, "Instagram tile %d" % i,
         "Home page and About page | Instagram grid, tile %d. Square, nothing is cropped." % i,
         "800×800", "1:1") for i in range(1, 9)]),
    ("About page | Instagram grid", [
        ("about_ig_%d_img" % i, "About tile %d" % i,
         "About page | Instagram grid, tile %d. Leave it empty and this tile "
         "shows whatever the home page's tile %d shows." % (i, i),
         "800×800", "1:1") for i in range(1, 9)]),
    ("About page | Instagram reel links", [
        ("about_ig_%d_reel" % i, "About reel link %d" % i,
         "About page | tapping tile %d opens this link. Empty falls back to the "
         "home page's link for the same tile. A URL, not an image." % i,
         "", "") for i in range(1, 9)]),
    ("Page banners", [
        ("catering_hero_img", "Catering page hero", "Catering page | the banner across the top.", "2560×1200", "21:10"),
        ("careers_hero_img", "Careers page hero", "Join Our Team page | the banner across the top.", "2560×1200", "21:10"),
        ("about_hero_img", "About page hero", "About page | the banner across the top.", "2560×1200", "21:10"),
        ("contact_hero_img", "Contact page hero", "Contact page | the banner across the top.", "2560×1200", "21:10"),
        ("deals_hero_img", "Deals page banner", "Deals page | the banner across the top.", "2560×1200", "21:10"),
        ("giftcards_hero_img", "Gift cards page banner", "Gift cards page | the banner across the top.", "2560×1200", "21:10"),
        ("rewards_hero_img", "Rewards page banner", "Rewards page | the banner across the top. This is the tallest banner on the site.", "2560×1440", "16:9"),
        ("faq_hero_img", "FAQ / help hero", "Help centre page | the banner across the top.", "2560×1200", "21:10"),
    ]),
    ("About page photos", [
        ("about_card1_img", "Story card 1 photo", "About page | the first of the two story cards.", "1200×900", "4:3"),
        ("about_card2_img", "Story card 2 photo", "About page | the second story card.", "1200×900", "4:3"),
        ("about_table_img", "“Meet us at the table” photo", "About page | the photo beside “Meet us at the table”.", "1200×900", "4:3"),
        ("about_crew_img", "Team photo", "About page | the tilted team photo near the bottom.", "1200×1200", "1:1"),
        ("about_kitchen_img", "Kitchen photo",
         "About page | the “inside our kitchen” photo beside the story text. "
         "Until you set it, it borrows the home page’s story photo.",
         "1200×1500", "4:5 portrait"),
        ("about_video_poster", "Video poster",
         "About page | the still shown before the video plays. Until you set it, "
         "it borrows the home page’s story photo.",
         "1920×1080", "16:9"),
        ("about_band_img", "Full-width band photo",
         "About page | the full-width photo band lower down. Until you set it, it "
         "borrows the home page’s catering banner.",
         "2400×1200", "2:1"),
    ]),
    ("Other page photos", [
        ("rewards_refer_img", "Rewards | refer a friend", "Rewards page | the “refer a friend” card.", "1200×900", "4:3"),
        ("giftcards_corporate_img", "Gift cards | corporate gifting", "Gift cards page | the corporate gifting card.", "1000×625", "16:10"),
        ("faq_support_img", "FAQ | support photo", "Help centre page | the photo beside the support text.", "1200×900", "4:3"),
        ("tracking_map_img", "Order tracking | map picture", "Order tracking page | the picture standing in for the live map.", "1600×1000", "16:10"),
    ]),
    ("Instagram reels (paste a reel link per tile)", [
        ("ig_%d_reel" % i, "Reel link for tile %d" % i,
         "Home page | tapping Instagram tile %d opens this link. A URL, not an image." % i,
         "", "") for i in range(1, 9)]),
    ("Videos (self-hosted)", [
        ("about_video", "About page video (MP4/WEBM, or paste a YouTube/Vimeo link)",
         "About page | plays in place of the photo. Upload MP4/WEBM or paste a YouTube/Vimeo link.",
         "1920×1080", "16:9"),
    ]),
    ("Sign in & sign up pages", [
        ("login_img", "Sign-in panel photo", "Sign-in page | the photo panel beside the form. Hidden on phones.", "1024×1400", "3:4 portrait"),
        ("register_img", "Sign-up panel photo", "Sign-up page | a very tall photo panel. Hidden on phones.", "1024×2200", "1:2 tall"),
        ("forgot_img", "Forgot-password panel photo", "Forgot-password page | the photo panel. Hidden on phones.", "1024×1400", "3:4 portrait"),
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
    # Pictures no longer travel with this form | each one is sent on its own to
    # /admin/inline-image the moment it is chosen, so one oversized file cannot
    # take the whole batch down with it. What is left here is the link boxes.
    for _title, slots in SITE_IMAGE_SLOTS:
        for slot in slots:
            key = slot[0]
            val = request.form.get(key, "").strip()
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
    return render_template("admin/features.html", features_spec=FEATURES,
                           current=flags, **_shell(store))


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


# ── On-page image swap (the editor bar, ?edit=1) ─────────────────────────
@bp.post("/admin/inline-image")
@roles_required(*ADMIN_ROLES)
def inline_image():
    """Set one image slot from the page itself.

    Same guard as inline-save: only keys the Site images registry knows about,
    so this cannot become a way to write arbitrary settings rows.
    """
    allowed = {slot[0] for _t, rows in SITE_IMAGE_SLOTS for slot in rows}
    key = (request.form.get("key") or "").strip()
    if key not in allowed:
        return {"ok": False, "error": "unknown image"}, 400

    # the About page's video slot takes MP4/WEBM, every other slot only images
    exts = VIDEO_EXTS if key.endswith("_video") else IMAGE_EXTS
    sent = request.files.get("file")
    url = _save_image(sent, "site-" + key.replace("_", "-"), exts, quiet=True)
    if sent and getattr(sent, "filename", "") and not url:
        # a file WAS chosen and we refused it; falling through to the url field
        # here would quietly clear the slot instead of reporting the problem
        return {"ok": False, "error": "That file type is not allowed here | use %s."
                % ", ".join(e.lstrip(".").upper() for e in exts)}, 400
    url = url or (request.form.get("url") or "").strip()
    row = SiteSetting.query.filter_by(key=key).first()
    if url:
        if row:
            row.value = url
        else:
            db.session.add(SiteSetting(key=key, value=url))
    elif row:
        db.session.delete(row)          # cleared → back to the built-in default
    db.session.commit()
    return {"ok": True, "key": key, "url": url}


# ── On-page section styling (the editor bar, ?edit=1) ────────────────────
TEXTSHADOW_CHOICES = [
    ("", "Default"), ("none", "None"),
    ("0 1px 2px rgba(0,0,0,.35)", "Subtle"),
    ("0 2px 10px rgba(0,0,0,.45)", "Soft glow"),
    ("0 4px 26px rgba(0,0,0,.55)", "Strong"),
    ("2px 2px 0 rgba(0,0,0,.85)", "Hard offset"),
]

ITALIC_CHOICES = [("", "Default"), ("normal", "Upright"), ("italic", "Italic")]

# "None" has to be a real stored value, not an empty one: an empty box means
# "inherit whatever was there", and the client asked for off to mean off.
TSSIDE_CHOICES = [("", "Leave as designed"), ("none", "No shadow"), ("bottom", "Bottom only"),
                  ("top", "Top only"), ("left", "Left only"), ("right", "Right only"),
                  ("all", "All sides")]

BGSIZE_CHOICES = [("", "Default"), ("cover", "Fill the section"),
                  ("contain", "Fit inside"), ("auto", "Original size")]
BGPOS_CHOICES = [("", "Default"), ("center", "Centre"), ("top", "Top"),
                 ("bottom", "Bottom"), ("left", "Left"), ("right", "Right")]
GRADDIR_CHOICES = [("", "Default"), ("180deg", "Top to bottom"), ("0deg", "Bottom to top"),
                   ("90deg", "Left to right"), ("270deg", "Right to left"),
                   ("135deg", "Diagonal")]
FILTER_CHOICES = [("", "None"), ("grayscale(1)", "Black & white"),
                  ("grayscale(.5)", "Muted"), ("sepia(.6)", "Warm / sepia"),
                  ("brightness(1.15)", "Brighter"), ("brightness(.8)", "Darker"),
                  ("contrast(1.2)", "More contrast"), ("saturate(1.4)", "More colour"),
                  ("blur(3px)", "Blurred")]
VALIGN_CHOICES = [("", "Default"), ("flex-start", "Top"), ("center", "Middle"),
                  ("flex-end", "Bottom")]
IMGFIT_CHOICES = [("", "Default"), ("cover", "Fill the frame"), ("contain", "Fit inside"),
                  ("fill", "Stretch"), ("scale-down", "Never enlarge")]
COLS_CHOICES = [("", "Default"), ("1", "1 per row"), ("2", "2"), ("3", "3"),
                ("4", "4"), ("5", "5"), ("6", "6")]
XTRAPOS_CHOICES = [("", "Below the section"), ("top", "Above the section")]
XTRAALIGN_CHOICES = [("auto", "Centre"), ("0 auto 0 0", "Left"), ("0 0 0 auto", "Right")]

SHADOW_CHOICES = [
    ("", "Default"), ("none", "None"),
    ("0 1px 3px rgba(20,20,20,.10)", "Soft"),
    ("0 4px 20px rgba(20,20,20,.10)", "Medium"),
    ("0 12px 40px rgba(20,20,20,.16)", "Deep"),
    ("0 20px 60px rgba(20,20,20,.28)", "Dramatic"),
]


@bp.post("/admin/inline-section-text")
@roles_required(*ADMIN_ROLES)
def inline_section_text():
    """Save one home-section word from the page itself."""
    data = request.get_json(silent=True) or {}
    section = (data.get("section") or "").strip()
    field = (data.get("field") or "").strip()
    value = (data.get("value") or "").strip()
    spec = spec_for(section)
    if not spec or field not in {f[0] for f in spec.get("fields", [])}:
        return {"ok": False, "error": "unknown field"}, 400

    row = PageSection.query.filter_by(page="home", key=section).first()
    if not row:
        row = PageSection(page="home", key=section, label=spec.get("label", section))
        db.session.add(row)
    cfg = dict(row.config or {})
    if value:
        cfg[field] = value
    else:
        cfg.pop(field, None)
    row.config = cfg
    db.session.commit()
    return {"ok": True}


@bp.post("/admin/inline-style-reset")
@roles_required(*ADMIN_ROLES)
def inline_style_reset():
    """Put a section | or a whole page | back to the design it shipped with.

    Only the style_* keys are dropped. Words the client wrote and pictures they
    uploaded are theirs and stay; this is "undo my restyling", not "undo my
    work".
    """
    data = request.get_json(silent=True) or {}
    page = (data.get("page") or "").strip()
    section = (data.get("section") or "").strip()
    if not page:
        return {"ok": False, "error": "which page?"}, 400

    q = PageSection.query.filter_by(page=page)
    if section:
        q = q.filter_by(key=section)
    cleared = 0
    for row in q.all():
        cfg = dict(row.config or {})
        styled = [k for k in cfg if k.startswith("style_")]
        if not styled:
            continue
        for k in styled:
            cfg.pop(k)
        row.config = cfg
        cleared += len(styled)
    db.session.commit()
    return {"ok": True, "cleared": cleared, "scope": section or page}


@bp.post("/admin/site-images/<key>/delete")
@roles_required(*ADMIN_ROLES)
def site_image_delete(key):
    """Remove a picture: forget the setting and delete the file we stored.

    A pasted link is only forgotten | it is not ours to delete. An upload we
    made is removed from disk as well, so clearing a slot does not quietly
    leave megabytes behind.
    """
    store = _admin_store()
    allowed = {slot[0] for _t, rows in SITE_IMAGE_SLOTS for slot in rows}
    if key not in allowed:
        abort(404)
    row = SiteSetting.query.filter_by(key=key).first()
    removed_file = False
    if row:
        val = row.value or ""
        if val.startswith("/static/img/uploads/"):
            # The value is whatever was typed into the link box, so the path it
            # implies is untrusted: "/static/img/uploads/../../.." would walk out
            # of the folder and delete something else entirely. Resolve it and
            # refuse anything that does not land inside uploads.
            updir = os.path.realpath(
                os.path.join(current_app.static_folder, "img", "uploads"))
            path = os.path.realpath(
                os.path.join(current_app.static_folder, *val.replace("/static/", "").split("/")))
            inside = path == updir or path.startswith(updir + os.sep)
            try:
                if inside and os.path.isfile(path):
                    os.remove(path); removed_file = True
                elif not inside:
                    current_app.logger.warning("refused to delete outside uploads: %s", val)
            except OSError:
                current_app.logger.warning("could not delete %s", path)
        db.session.delete(row)
        db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "deleted": bool(row), "file_removed": removed_file}
    flash("Picture removed | that slot is back to the built-in image.", "success")
    return redirect("/admin/site-images" + _qs(store))


@bp.post("/admin/inline-style-image")
@roles_required(*ADMIN_ROLES)
def inline_style_image():
    """Upload a section's background picture straight from the page."""
    page = (request.form.get("page") or "").strip()
    section = (request.form.get("section") or "").strip()
    if not page or not section:
        return {"ok": False, "error": "unknown section"}, 400
    key = (request.form.get("key") or "style_bgimage").strip()
    if key not in ("style_bgimage", "style_xtraimg"):
        return {"ok": False, "error": "unknown image"}, 400
    url = _save_image(request.files.get("file"),
                      "sec-%s-%s-%s" % (page, section, key.replace("style_", "")))
    if not url:
        return {"ok": False, "error": "no image"}, 400
    row = PageSection.query.filter_by(page=page, key=section).first()
    if not row:
        row = PageSection(page=page, key=section, label=section.replace("_", " ").title())
        db.session.add(row)
    cfg = dict(row.config or {}); cfg[key] = url; row.config = cfg
    db.session.commit()
    return {"ok": True, "url": url, "key": key}


@bp.get("/admin/inline-style")
@roles_required(*ADMIN_ROLES)
def inline_style_read():
    """What is currently saved for one section.

    The panel used to read its starting values back out of the CSS variables on
    the element, which cannot work for the controls that have no variable of
    their own | the four heading-shadow fields are composed into a single
    variable on the server. Those controls came up blank after a reload and
    made a saved setting look lost.
    """
    page = (request.args.get("page") or "").strip()
    section = (request.args.get("section") or "").strip()
    if not page or not section:
        return {"ok": False, "error": "which section?"}, 400
    row = PageSection.query.filter_by(page=page, key=section).first()
    cfg = dict(row.config or {}) if row else {}
    return {"ok": True, "config": {k: v for k, v in cfg.items() if k.startswith("style_")}}


@bp.post("/admin/inline-style")
@roles_required(*ADMIN_ROLES)
def inline_style():
    """Restyle one section from the page itself.

    Writes to the same PageSection.config the Visual editor and Page design
    write to | one place the style lives, so the three ways of reaching it can
    never disagree.
    """
    data = request.get_json(silent=True) or {}
    page = (data.get("page") or "").strip()
    section = (data.get("section") or "").strip()
    key = (data.get("key") or "").strip()
    value = (data.get("value") or "").strip()

    # RETIRED_STYLE_FIELDS are deliberately absent: they still render, so no
    # existing section changes, but nothing may write them any more.
    allowed = {f[0] for f in DESIGN_FIELDS} | {
        "style_overlay", "style_overlaycolor", "style_cardbg", "style_cardborder",
        "style_cardhead", "style_cardtext", "style_cardradius", "style_shadow",
        "style_imgoverlay", "style_imgradius",
        "style_divider", "style_maxw",
        "style_imgh", "style_imgfit", "style_cardcols", "style_cardminw",
        "style_cardw", "style_cardh", "style_gap", "style_squigcolor", "style_squigw", "style_navlink",
        "style_iconcolor", "style_logoh", "style_bgimage", "style_xtraimg",
        "style_xtrapos", "style_xtraw", "style_xtrah", "style_xtraradius",
        "style_xtraborder", "style_xtraborderw", "style_xtrashadow",
        "style_xtraalign"} | TEXT_ROLE_KEYS | CTA_KEYS
    # tablet / desktop copies of every allowed section key
    allowed |= {k + bp for k in list(allowed)
                if not k.endswith(("md", "lg"))
                for bp in ("md", "lg")}

    def _lock_other_breakpoints(cfg, key):
        """Before a phone (base) edit, copy base values into md/lg when those
        keys are still missing | otherwise clearing a shared base style would
        wipe tablet/desktop that had been inheriting it."""
        if key.endswith("md") or key.endswith("lg"):
            return
        # style_title_tsside → prefix style_title_, prop tsside
        # style_shadow → prefix style_, prop shadow
        m = None
        for role, _ in TEXT_ROLE_LABELS:
            p = "style_%s_" % role
            if key.startswith(p):
                m = (p, key[len(p):])
                break
        if not m and key.startswith("style_"):
            m = ("style_", key[len("style_"):])
        if not m:
            return
        prefix, prop = m
        # shadow is four keys; lock the whole group together
        props = (("tsside", "tsdist", "tsblur", "tscolor")
                 if prop in ("tsside", "tsdist", "tsblur", "tscolor")
                 else (prop,))
        for bp in ("md", "lg"):
            for p in props:
                src = prefix + p
                dst = prefix + p + bp
                if dst not in cfg and src in cfg:
                    cfg[dst] = cfg[src]

    # A retired key may still be CLEARED, never set. A section saved before the
    # per-element system can carry one, and with no way to remove it the client
    # would be stuck with a setting that moves several kinds of text at once and
    # appears nowhere in the panel.
    clearing_old = key in RETIRED_STYLE_FIELDS and not value
    if (key not in allowed and not clearing_old) or not page or not section:
        return {"ok": False, "error": "unknown field"}, 400
    if not style_value_ok(value):
        return {"ok": False, "error": "that is not a valid value"}, 400

    row = PageSection.query.filter_by(page=page, key=section).first()
    if not row:
        row = PageSection(page=page, key=section, label=section.replace("_", " ").title())
        db.session.add(row)
    cfg = dict(row.config or {})
    _lock_other_breakpoints(cfg, key)
    if value:
        cfg[key] = value
    else:
        cfg.pop(key, None)
    row.config = cfg
    db.session.commit()
    # hand back the rebuilt inline style: several controls (the heading shadow)
    # are composed from more than one field, so the page cannot work it out
    style_of = current_app.jinja_env.globals.get("pb_section_style")
    return {"ok": True, "key": key, "value": value,
            "style": style_of(cfg) if style_of else ""}


# ── Page builder (home page sections: order, visibility, text, theme) ────
@bp.get("/admin/page-builder")
@roles_required(*ADMIN_ROLES)
def page_builder():
    """Retired | the Visual editor does everything this screen did.

    This was a drag-to-reorder list with a show/hide checkbox. /admin/canvas
    reorders, shows/hides, edits each section's text AND restyles it, so two
    tabs were offering the same job with different amounts of it. The route
    stays as a redirect: bookmarks and any older link still land somewhere
    useful instead of on a 404.
    """
    return redirect("/admin/canvas" + _qs(_admin_store()))


def _apply_page_builder_form():
    """Persist the submitted order / visibility / text / theme onto the home
    section rows (does NOT commit | the caller commits)."""
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
    overridable = {o[0] for o in builder_overridable() if o[0] not in taken}
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
            # all the others | which is exactly what a per-page editor posts.
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


# ── Email templates (subjects + body copy for customer emails) ───────────
@bp.get("/admin/email-templates")
@roles_required(*ADMIN_ROLES)
def email_templates():
    store = _admin_store()
    current = {s.key: s.value for s in SiteSetting.query.all() if s.value}
    brand = current_app.config.get("BRAND_NAME", "")
    defaults = {**email_layout_defaults(brand), **email_template_defaults(brand)}
    return render_template("admin/email_templates.html", groups=templates_for_admin(),
                           layout_fields=EMAIL_LAYOUT, placeholders=EMAIL_PLACEHOLDERS,
                           current=current, defaults=defaults, **_shell(store))


@bp.get("/admin/email-templates/preview/<tpl_key>")
@roles_required(*ADMIN_ROLES)
def email_templates_preview(tpl_key):
    known = {tpl[0] for _g, _l, _i, tpls in EMAIL_TEMPLATE_GROUPS for tpl in tpls}
    if tpl_key not in known:
        abort(404)
    ctx = preview_context(tpl_key)
    rows = preview_rows(tpl_key)
    cta = "https://oksmashedburger.com/menu"
    _, _, html = render_email(tpl_key, ctx, rows=rows, cta_href=cta,
                              brand=current_app.config.get("BRAND_NAME") or None)
    return Response(html, mimetype="text/html; charset=utf-8")


@bp.post("/admin/email-image")
@roles_required(*ADMIN_ROLES)
def email_image():
    allowed = email_image_keys()
    key = (request.form.get("key") or "").strip()
    if key not in allowed:
        return jsonify(ok=False, error="unknown image slot"), 400
    sent = request.files.get("file")
    slug = "email-" + key.replace("_", "-")
    url = _save_image(sent, slug, quiet=True)
    if sent and getattr(sent, "filename", "") and not url:
        return jsonify(ok=False, error="That file type is not allowed here | use JPG, PNG, GIF or WEBP."), 400
    url = url or (request.form.get("url") or "").strip()
    row = SiteSetting.query.filter_by(key=key).first()
    if url:
        if row:
            row.value = url
        else:
            db.session.add(SiteSetting(key=key, value=url))
    elif row:
        db.session.delete(row)
    db.session.commit()
    return jsonify(ok=True, key=key, url=url)


@bp.post("/admin/email-templates")
@roles_required(*ADMIN_ROLES)
def email_templates_save():
    store = _admin_store()
    brand = current_app.config.get("BRAND_NAME", "")
    defaults = {**email_layout_defaults(brand), **email_template_defaults(brand)}
    save_kind = request.form.get("save_kind", "template")
    allowed = set()
    if save_kind == "layout":
        allowed = set(email_layout_defaults(brand))
    else:
        tpl_key = (request.form.get("tpl_key") or "").strip()
        for _g, _l, _i, tpls in EMAIL_TEMPLATE_GROUPS:
            for key, _tl, flds in tpls:
                if key == tpl_key:
                    for field, _fl, _def, _kind in flds:
                        allowed.add("email_%s_%s" % (tpl_key, field))
                    allowed.add("email_%s_custom_html" % tpl_key)
                    break
    for key in allowed:
        if key not in request.form:
            continue
        raw = request.form.get(key)
        val = (raw or "").strip() if not key.endswith("_custom_html") else (raw or "")
        if key.endswith("_custom_html"):
            val = val.strip()
        setting = SiteSetting.query.filter_by(key=key).first()
        if val and val != (defaults.get(key) or ""):
            if setting:
                setting.value = val
            else:
                db.session.add(SiteSetting(key=key, value=val))
        elif setting:
            db.session.delete(setting)
    db.session.commit()
    flash("Email template saved.", "success")
    anchor = "design" if save_kind == "layout" else (request.form.get("tpl_key") or "")
    return redirect("/admin/email-templates" + _qs(store) + ("#" + anchor if anchor else ""))


# ── Visual canvas editor (drag/reorder + live restyle of home sections) ──
# Only faces the page can actually render: the two brand webfonts plus stacks
# built from what every OS already ships. A face nobody has installed would
# silently fall back and the client would think the control was broken.
# (css stack, label, Google family to load | blank means it needs no webfont)
#
# A face the page never loads would silently fall back and the control would
# look broken, so the families here are fetched on demand: a page only asks
# Google for the ones its own sections actually use (see google_fonts_link).
CANVAS_FONTS = [
    ("", "Default", ""),
    # already loaded site-wide
    ("'Poppins',sans-serif", "Poppins | bold display", "Poppins:wght@400;500;600;700;800;900"),
    ("'Quicksand',sans-serif", "Quicksand | rounded", "Quicksand:wght@400;500;600;700"),
    ("'Inter',sans-serif", "Inter | clean", "Inter:wght@300;400;500;600;700;800"),
    # display / headline faces
    ("'Anton',sans-serif", "Anton | poster", "Anton"),
    ("'Bebas Neue',sans-serif", "Bebas Neue | tall caps", "Bebas+Neue"),
    ("'Oswald',sans-serif", "Oswald | condensed", "Oswald:wght@300;400;500;600;700"),
    ("'Archivo Black',sans-serif", "Archivo Black | heavy", "Archivo+Black"),
    ("'Righteous',cursive", "Righteous | retro diner", "Righteous"),
    ("'Permanent Marker',cursive", "Permanent Marker | handwritten", "Permanent+Marker"),
    # text faces
    ("'Montserrat',sans-serif", "Montserrat | modern", "Montserrat:wght@300;400;500;600;700;800;900"),
    ("'Work Sans',sans-serif", "Work Sans | neutral", "Work+Sans:wght@300;400;500;600;700;800"),
    ("'Nunito',sans-serif", "Nunito | soft", "Nunito:wght@300;400;500;600;700;800;900"),
    ("'Space Grotesk',sans-serif", "Space Grotesk | technical", "Space+Grotesk:wght@300;400;500;600;700"),
    # more display / headline
    ("'Alfa Slab One',serif", "Alfa Slab | heavy slab", "Alfa+Slab+One"),
    ("'Bungee',sans-serif", "Bungee | signage", "Bungee"),
    ("'Fredoka',sans-serif", "Fredoka | friendly round", "Fredoka:wght@300;400;500;600;700"),
    ("'Titan One',cursive", "Titan One | chunky", "Titan+One"),
    ("'Bowlby One SC',cursive", "Bowlby | fat caps", "Bowlby+One+SC"),
    ("'Passion One',cursive", "Passion One | condensed bold", "Passion+One:wght@400;700;900"),
    ("'Staatliches',cursive", "Staatliches | poster caps", "Staatliches"),
    ("'Rampart One',cursive", "Rampart | outlined", "Rampart+One"),
    # more text faces
    ("'Rubik',sans-serif", "Rubik | rounded sans", "Rubik:wght@300;400;500;600;700;800;900"),
    ("'DM Sans',sans-serif", "DM Sans | geometric", "DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,700"),
    ("'Manrope',sans-serif", "Manrope | modern sans", "Manrope:wght@300;400;500;600;700;800"),
    ("'Karla',sans-serif", "Karla | grotesque", "Karla:wght@300;400;500;600;700;800"),
    ("'Barlow',sans-serif", "Barlow | low contrast", "Barlow:wght@300;400;500;600;700;800;900"),
    ("'Cabin',sans-serif", "Cabin | humanist", "Cabin:wght@400;500;600;700"),
    # more serif
    ("'Merriweather',serif", "Merriweather | sturdy serif", "Merriweather:wght@300;400;700;900"),
    ("'Bitter',serif", "Bitter | slab serif", "Bitter:wght@300;400;500;600;700;800"),
    ("'Abril Fatface',serif", "Abril Fatface | display serif", "Abril+Fatface"),
    # handwriting
    ("'Caveat',cursive", "Caveat | handwriting", "Caveat:wght@400;500;600;700"),
    ("'Pacifico',cursive", "Pacifico | script", "Pacifico"),
    ("'Shadows Into Light',cursive", "Shadows | light hand", "Shadows+Into+Light"),
    # serif
    ("'Playfair Display',serif", "Playfair | editorial serif", "Playfair+Display:wght@400;500;600;700;800;900"),
    ("'Lora',serif", "Lora | readable serif", "Lora:wght@400;500;600;700"),
    ("Georgia,'Times New Roman',serif", "Georgia | system serif", ""),
    # system stacks, no download needed
    ("'Trebuchet MS',sans-serif", "Trebuchet | friendly", ""),
    ("'Segoe UI',system-ui,sans-serif", "Segoe / system", ""),
    ("'Helvetica Neue',Helvetica,Arial,sans-serif", "Helvetica | neutral", ""),
    ("'Arial Black',Impact,sans-serif", "Arial Black | heavy", ""),
    ("Impact,Haettenschweiler,sans-serif", "Impact | condensed", ""),
    ("'Courier New',monospace", "Courier | mono", ""),
    ("ui-monospace,'Cascadia Mono',Consolas,monospace", "Mono | modern", ""),
]

# The full library the designer offers: 160 families, each one checked against
# Google Fonts with its real weight list read back, grouped so a picker can be
# searched and browsed rather than scrolled. CANVAS_FONTS stays as it was so the
# older screens and google_fonts_link() keep working unchanged.
from app.fonts import (FONT_LIBRARY, CATEGORIES as FONT_CATEGORIES,  # noqa: E402
                       GOOGLE_SPEC as FONT_GOOGLE_SPEC,
                       WEIGHTS_FOR as FONT_WEIGHTS_FOR)

_LEGACY_STACKS = {f[0] for f in CANVAS_FONTS}

# (stack, label, category, weights) | everything the picker needs in one place
FONT_PICKER = [(stack, family, category, weights)
               for family, stack, category, weights in FONT_LIBRARY]

# what the admin <select>s show | (value, label) only
CANVAS_FONT_CHOICES = ([("", "Default")] +
                       [(stack, family) for stack, family, _c, _w in FONT_PICKER])

WEIGHT_LABELS = {100: "Thin", 200: "Extralight", 300: "Light", 400: "Regular",
                 500: "Medium", 600: "Semibold", 700: "Bold", 800: "Extrabold",
                 900: "Black"}

CANVAS_WEIGHTS = [("", "Default")] + [(str(w), WEIGHT_LABELS[w])
                                      for w in (100, 200, 300, 400, 500, 600, 700, 800, 900)]

CANVAS_CASES = [("", "As written"), ("none", "Normal"), ("uppercase", "UPPERCASE"),
                ("capitalize", "Capitalise"), ("lowercase", "lowercase")]


@bp.get("/admin/canvas")
@roles_required(*ADMIN_ROLES)
def canvas():
    """One screen for every page: the sections on the left, the page in the
    middle, the settings for whatever is selected on the right.

    It used to be the home page's screen alone, and every other page was a long
    form of a hundred boxes with no picture of what they did. The home page can
    also be reordered and its sections switched off, which the inner pages
    cannot | their running order is part of what each page IS | so those two
    affordances simply do not appear there.
    """
    store = _admin_store()
    page = (request.args.get("page") or "home").strip()
    defaults = resolved_defaults(current_app.config.get("BRAND_NAME", ""))
    state = []

    if page == "home":
        for row in home_sections_ordered():
            spec = spec_for(row.key)
            fields = [{"key": f, "label": lbl,
                       "default": (defaults.get(row.key, {}).get(f) or d or "")}
                      for f, lbl, d in spec.get("fields", [])]
            state.append({
                "key": row.key, "sid": row.id, "label": row.label,
                "enabled": bool(row.enabled), "custom": bool(spec.get("custom")),
                "config": row.config or {}, "fields": fields,
            })
        page_url, page_label = "/", "Home page"
    else:
        spec = INNER_PAGE_BY_KEY.get(page)
        if not spec:
            abort(404)
        for s in inner_sections(page):
            state.append({
                "key": s["key"], "sid": s["id"], "label": s["label"],
                "enabled": True, "custom": False,
                "config": s["config"], "fields": [],
            })
        page_url, page_label = spec["url"], spec["label"]

    return render_template("admin/canvas.html", inner_pages=INNER_PAGES, state=state,
                           page=page, page_url=page_url, page_label=page_label,
                           can_reorder=(page == "home"),
                           fonts=CANVAS_FONT_CHOICES,
                           weights=CANVAS_WEIGHTS, cases=CANVAS_CASES, **_shell(store))


@bp.post("/admin/canvas/save")
@roles_required(*ADMIN_ROLES)
def canvas_save():
    data = request.get_json(silent=True) or {}
    items = data.get("sections", [])
    # which page's sections these are. Only the home page can be reordered or
    # have sections switched off; an inner page's order is part of what the
    # page is, so only its styling comes back here.
    page = (data.get("page") or "home").strip()
    if page != "home" and page not in INNER_PAGE_BY_KEY:
        return {"ok": False, "error": "unknown page"}, 400
    rows = {s.key: s for s in PageSection.query.filter_by(page=page).all()}
    for i, item in enumerate(items):
        key = item.get("key")
        row = rows.get(key)
        if not row and page != "home":
            # an inner page's section has no row until something is saved for it
            label = next((s["label"] for s in INNER_PAGE_BY_KEY[page]["sections"]
                          if s["key"] == key), key)
            row = PageSection(page=page, key=key, label=label, enabled=True, sort_order=i)
            db.session.add(row)
            rows[key] = row
        if not row:
            continue
        if page != "home":
            cfg = item.get("config")
            if isinstance(cfg, dict):
                kept = dict(row.config or {})
                for k, v in cfg.items():
                    if not str(k).startswith("style_"):
                        kept[k] = v
                    elif k in RETIRED_STYLE_FIELDS:
                        continue
                    elif style_value_ok(v):
                        kept[k] = v
                for k in CANVAS_STYLE_KEYS:
                    if k in kept and k not in cfg:
                        kept.pop(k)
                row.config = kept
            continue
        row.sort_order = i
        row.enabled = bool(item.get("enabled", True))
        cfg = item.get("config")
        if isinstance(cfg, dict):
            # A merge, not a replacement. This screen used to store whatever
            # arrived, which meant it also DELETED every setting it does not
            # know about: a tab opened before someone styled a heading on the
            # page would, on Save, quietly wipe that heading's settings. It
            # only offers section-level things now, so anything else it sends
            # is just what it happened to load | the row keeps its own.
            kept = dict(row.config or {})
            for k, v in cfg.items():
                if not str(k).startswith("style_"):
                    kept[k] = v                     # content and layout fields
                elif k in RETIRED_STYLE_FIELDS:
                    continue                        # never written again
                elif style_value_ok(v):
                    kept[k] = v
            # a control this screen owns, cleared on this screen, really clears
            for k in CANVAS_STYLE_KEYS:
                if k in kept and k not in cfg:
                    kept.pop(k)
            row.config = kept
    db.session.commit()
    return {"ok": True}


# ── GrapesJS drag-drop page builder (standalone pages at /p/<slug>) ───────
@bp.get("/admin/builder")
@roles_required(*ADMIN_ROLES)
def builder_list():
    store = _admin_store()
    pages = BuilderPage.query.order_by(BuilderPage.created_at.desc()).all()
    taken = {p.override_path for p in pages if p.override_path}
    overridable = [o for o in builder_overridable() if o[0] not in taken]
    # a home page holding content of its own has taken `/` away from the
    # section system, so offer to hand it back
    from ..website import _is_pure_section_page
    frozen_home = {p.id for p in pages if p.is_home and not _is_pure_section_page(p)}
    return render_template("admin/builder_list.html", pages=pages, frozen_home=frozen_home,
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


# Which storefront pages the builder can take over. Derived from the page
# registry rather than typed out, so a page added there shows up here on its
# own instead of quietly missing from the list.
#
# `live` marks a page whose body is data | the menu, the store list, the cart.
# Rebuilding one of those freezes today's data into static HTML, which is a
# much bigger deal than freezing a copy block, so the screen says so per page.
_BUILDER_TEMPLATES_BY_PAGE = {
    "menu": ("menu/menu.html", True),
    "locations": ("stores/locations.html", True),
    "cart": ("cart/cart.html", True),
}


def builder_overridable():
    """[(path, label, template, live), …] for every page that can be rebuilt."""
    from app.models.page import INNER_PAGES
    out = []
    for spec in INNER_PAGES:
        page = spec["page"]
        tpl, live = _BUILDER_TEMPLATES_BY_PAGE.get(page, ("website/%s.html" % page, False))
        out.append((spec["url"], spec["label"], tpl, live))
    return out




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
    ov = next((o for o in builder_overridable() if o[0] == override), None)
    opath = None
    if ov:
        if BuilderPage.query.filter_by(override_path=ov[0]).first():
            flash("A builder page already replaces %s | edit or delete that one." % ov[0], "error")
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


def _home_placeholders():
    """The home as the builder should hold it: one live block per section.

    Every section is a `data-dyn` placeholder, so `expand_dynamic` renders it
    from its own PageSection config every time the page is served. Baking the
    sections into static HTML here | which is what this used to do for the nine
    sections that are not fed by the menu/store tables | froze the home page:
    from that moment `/` served a snapshot, so switching a section off,
    reordering, restyling or editing its words and pictures did nothing at all.

    The order comes from the Page Builder, not from the registry, and the
    admin's own custom blocks are included | seeding from the static key list
    would show them in a different order to the live page and leave custom
    blocks out of the builder altogether.
    """
    try:
        keys = [r.key for r in home_sections_ordered()]
    except Exception:
        keys = list(DYNAMIC_SECTION_KEYS)
    for k in DYNAMIC_SECTION_KEYS:          # a registry section with no row yet
        if k not in keys:
            keys.append(k)
    return "".join('<section data-dyn="%s"></section>' % k for k in keys)


@bp.post("/admin/builder/new-home")
@roles_required(*ADMIN_ROLES)
def builder_new_home():
    """Create (or open) a drag-drop HOME page pre-loaded with the real home."""
    store = _admin_store()
    existing = BuilderPage.query.filter_by(is_home=True).first()
    if existing:
        return redirect("/admin/builder/%d" % existing.id + _qs(store))
    page = BuilderPage(title="Home page", slug=unique_page_slug("home"),
                       html=_home_placeholders(), css="", gjs={},
                       published=True, is_home=True)
    db.session.add(page)
    db.session.commit()
    flash("Home page loaded into the builder | reorder its sections and drop new blocks around them.", "success")
    return redirect("/admin/builder/%d" % page.id + _qs(store))


@bp.post("/admin/builder/<int:pid>/detach-home")
@roles_required(*ADMIN_ROLES)
def builder_detach_home(pid):
    """Hand a frozen home page back to the section system.

    A page that has real content of its own owns `/` completely, which is right
    when the admin built something there on purpose and wrong when it happened
    by accident. This puts the section placeholders back so the home is once
    again described by Page Builder, Page design and on-page editing.

    Nothing is thrown away: whatever was built here is kept as a draft page, so
    an admin who did mean to build a home by hand can get it back. Words and
    pictures were never in this HTML anyway | they live in the sections.
    """
    store = _admin_store()
    page = BuilderPage.query.get_or_404(pid)
    if not page.is_home:
        abort(404)          # only the home page is served this way
    if (page.html or "").strip():
        copy = BuilderPage(
            title=(page.title or "Home page") + " (built copy)",
            slug=unique_page_slug((page.slug or "home") + "-built-copy"),
            html=page.html, css=page.css, gjs=page.gjs,
            published=False, is_home=False)
        if hasattr(page, "head_code"):
            copy.head_code = page.head_code      # analytics/pixel snippets too
        db.session.add(copy)
    page.html = _home_placeholders()
    page.css = ""
    page.gjs = {}
    if hasattr(page, "head_code"):
        page.head_code = ""
    db.session.commit()
    flash("Home page handed back to its sections. What you had built is saved as a draft copy.", "success")
    return redirect("/admin/builder" + _qs(store))


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
    products = (
        Product.query.join(Category, Product.category_id == Category.id)
        .order_by(Category.sort_order, Product.sort_order, Product.name)
        .all()
    )
    for p in products:
        mi = existing.get(p.id)
        rows.append({
            "product": p,
            "listed": mi.is_listed if mi else False,
            "available": mi.is_available if mi else True,
            "price": float(mi.price_override) if (mi and mi.price_override is not None) else float(p.base_price),
        })
    return render_template("admin/menu.html", rows=rows,
                           categories=Category.query.order_by(Category.sort_order).all(),
                           addon_library=AddonLibrary.query.order_by(AddonLibrary.sort_order, AddonLibrary.name).all(),
                           **_shell(store))


@bp.post("/admin/menu/<int:pid>")
@roles_required(*ADMIN_ROLES)
def menu_save(pid):
    store = _admin_store()
    if not store:
        flash("Pick a location first.", "error")
        return redirect("/admin/menu")
    product = Product.query.get_or_404(pid)
    mi = StoreMenuItem.query.filter_by(store_id=store.id, product_id=pid).first()
    if not mi:
        mi = StoreMenuItem(store_id=store.id, product_id=pid)
        db.session.add(mi)
    mi.is_listed = bool(request.form.get("listed"))
    mi.is_available = bool(request.form.get("available"))
    price = request.form.get("price", type=float)
    mi.price_override = round(price, 2) if (price is not None and abs(price - float(product.base_price)) > 0.001) else None
    sort_order = request.form.get("sort_order", type=int)
    if sort_order is not None:
        product.sort_order = sort_order
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
    attached_lib_ids = {a.library_id for a in product.addons if a.library_id}
    return render_template(
        "admin/product_modifiers.html",
        product=product,
        addon_library=AddonLibrary.query.filter_by(is_active=True)
        .order_by(AddonLibrary.sort_order, AddonLibrary.name).all(),
        attached_lib_ids=attached_lib_ids,
        **_shell(store),
    )


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
def addon_attach(pid):
    store = _admin_store()
    product = Product.query.get_or_404(pid)
    lib_id = request.form.get("library_id", type=int)
    if lib_id:
        lib = AddonLibrary.query.get(lib_id)
        if not lib or not lib.is_active:
            flash("Pick a valid shared add-on.", "error")
            return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))
        if ProductAddon.query.filter_by(product_id=pid, library_id=lib.id).first():
            flash(f"“{lib.name}” is already attached.", "error")
            return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))
        db.session.add(ProductAddon(
            product=product, library=lib, name=lib.name, price=lib.price,
            sort_order=lib.sort_order or 0,
            is_required=bool(request.form.get("is_required")),
        ))
        db.session.commit()
        flash(f"Attached “{lib.name}”.", "success")
        return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))

    # Legacy / item-only add-on (keeps existing production behaviour).
    name = request.form.get("name", "").strip()
    if not name:
        flash("Enter an add-on name or pick one from the library.", "error")
        return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))
    try:
        price = Decimal(request.form.get("price") or "0")
    except InvalidOperation:
        price = Decimal("0")
    db.session.add(ProductAddon(
        product=product, name=name, price=price,
        is_required=bool(request.form.get("is_required")),
    ))
    db.session.commit()
    flash(f"Added item-only add-on “{name}”.", "success")
    return redirect(f"/admin/menu/{pid}/modifiers" + _qs(store))


@bp.post("/admin/menu/addons/<int:aid>/edit")
@roles_required(*ADMIN_ROLES)
def addon_edit(aid):
    store = _admin_store()
    a = ProductAddon.query.get_or_404(aid)
    if a.library_id:
        flash("Shared add-ons are edited on the menu page | changes sync to every attached item.", "error")
        return redirect(f"/admin/menu/{a.product_id}/modifiers" + _qs(store))
    name = request.form.get("name", "").strip()
    if name:
        a.name = name
    try:
        a.price = Decimal(request.form.get("price") or str(a.price))
    except InvalidOperation:
        pass
    a.is_required = bool(request.form.get("is_required"))
    db.session.commit()
    flash("Add-on updated.", "success")
    return redirect(f"/admin/menu/{a.product_id}/modifiers" + _qs(store))


@bp.post("/admin/menu/addons/<int:aid>/required")
@roles_required(*ADMIN_ROLES)
def addon_required(aid):
    store = _admin_store()
    a = ProductAddon.query.get_or_404(aid)
    a.is_required = bool(request.form.get("is_required"))
    db.session.commit()
    flash("Add-on updated.", "success")
    return redirect(f"/admin/menu/{a.product_id}/modifiers" + _qs(store))


@bp.post("/admin/catalog/addons")
@roles_required(*ADMIN_ROLES)
def addon_library_add():
    store = _admin_store()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Add-on name is required.", "error")
        return redirect("/admin/menu" + _qs(store))
    if AddonLibrary.query.filter(db.func.lower(AddonLibrary.name) == name.lower()).first():
        flash(f"“{name}” already exists in the shared library.", "error")
        return redirect("/admin/menu" + _qs(store))
    try:
        price = Decimal(request.form.get("price") or "0")
    except InvalidOperation:
        price = Decimal("0")
    db.session.add(AddonLibrary(
        name=name, price=price,
        sort_order=request.form.get("sort_order", type=int) or 0,
    ))
    db.session.commit()
    flash(f"Shared add-on “{name}” created.", "success")
    return redirect("/admin/menu" + _qs(store))


@bp.post("/admin/catalog/addons/<int:lid>/edit")
@roles_required(*ADMIN_ROLES)
def addon_library_edit(lid):
    store = _admin_store()
    lib = AddonLibrary.query.get_or_404(lid)
    name = request.form.get("name", "").strip()
    if name:
        lib.name = name
    try:
        lib.price = Decimal(request.form.get("price") or str(lib.price))
    except InvalidOperation:
        pass
    if request.form.get("sort_order") is not None:
        lib.sort_order = request.form.get("sort_order", type=int) or 0
    db.session.flush()
    for link in ProductAddon.query.filter_by(library_id=lib.id).all():
        link.name = lib.name
        link.price = lib.price
        link.sort_order = lib.sort_order or 0
    db.session.commit()
    flash(f"“{lib.name}” updated and synced to attached items.", "success")
    return redirect("/admin/menu" + _qs(store))


@bp.post("/admin/catalog/addons/<int:lid>/delete")
@roles_required(*ADMIN_ROLES)
def addon_library_delete(lid):
    store = _admin_store()
    lib = AddonLibrary.query.get_or_404(lid)
    if ProductAddon.query.filter_by(library_id=lib.id).count():
        lib.is_active = False
        db.session.commit()
        flash(f"“{lib.name}” is in use | deactivated instead of deleted.", "success")
    else:
        db.session.delete(lib)
        db.session.commit()
        flash(f"“{lib.name}” removed from the library.", "success")
    return redirect("/admin/menu" + _qs(store))


@bp.post("/admin/menu/addons/<int:aid>/delete")
@roles_required(*ADMIN_ROLES)
def addon_delete(aid):
    store = _admin_store()
    a = ProductAddon.query.get_or_404(aid)
    pid = a.product_id
    db.session.delete(a)
    db.session.commit()
    flash("Add-on removed from this item.", "success")
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


def _save_image(file, slug, exts=IMAGE_EXTS, quiet=False):
    """Save an uploaded file under /static/img/uploads and return its URL.

    `exts` lets a caller widen the whitelist, e.g. the About page video slot
    accepts MP4/WEBM. Everything else still only takes images.

    `quiet` is for the JSON endpoints: a flash raised here would sit in the
    session and surface on whatever page the admin opened next, long after they
    had already been told what went wrong.
    """
    if not file or not getattr(file, "filename", ""):
        return None
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in exts:
        if not quiet:
            flash("Unsupported file type | allowed: %s." % ", ".join(e.lstrip(".").upper() for e in exts), "error")
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
    name = product.name
    OrderItem.query.filter_by(product_id=pid).update({"product_id": None})
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
    _img = _save_image(request.files.get("image_file"), f"cat-{_unique_slug(name, Category)}")
    _img = _img or request.form.get("image_url", "").strip() or None
    db.session.add(Category(slug=_unique_slug(name, Category), name=name,
                            icon=request.form.get("icon", "").strip() or "utensils",
                            description=request.form.get("description", "").strip() or None,
                            image_url=_img,
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
    # Uploaded file wins; fallback to URL field; keep existing if neither given
    _uploaded = _save_image(request.files.get("image_file"), f"cat-{c.slug}")
    if _uploaded:
        c.image_url = _uploaded
    elif "image_url" in request.form:
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
    spec = next((p for p in PROVIDERS if p["key"] == provider), None)
    secret_keys = {f["key"] for f in (spec or {}).get("fields", []) if f.get("secret")}
    for key, val in request.form.items():
        if key.startswith("cfg_"):
            k = key[4:]
            if k in secret_keys and not val.strip() and cfg.get(k):
                continue
            cfg[k] = val.strip()
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
    # Optional location photo
    uploaded = _save_image(request.files.get("image_file"), f"store-{s.slug}")
    if uploaded:
        s.image_url = uploaded
    elif request.form.get("image_url", "").strip():
        s.image_url = request.form.get("image_url").strip()

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
    # Location photo: uploaded file wins over URL
    uploaded = _save_image(request.files.get("image_file"), f"store-{s.slug}")
    if uploaded:
        s.image_url = uploaded
    elif "image_url" in request.form:
        s.image_url = request.form.get("image_url", "").strip() or s.image_url
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
        flash("This location has orders | deactivate it instead of deleting.", "error")
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
        flash("Imported %d items from the website | they are yours to edit now." % n, "success")
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
        # never orphan delivery history | retire the driver instead
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
    flash("Published | %s's review is live on the site." % row.display_name, "success")
    return redirect(request.form.get("next") or "/admin/reviews")


@bp.post("/admin/reviews/<int:rid>/reject")
@roles_required(*ADMIN_ROLES)
def review_reject(rid):
    _moderate(rid, "rejected")
    flash("Rejected | it stays hidden from the site.", "success")
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
    THEME_TOKENS, FONT_CHOICES, THEME_GROUPS, SHADOW_PRESETS, theme_values, theme_css,
)


@bp.get("/admin/theme")
@roles_required("super_admin", "franchise_owner")
def theme():
    store = _admin_store()
    return render_template("admin/theme.html",
                           tokens=THEME_TOKENS, fonts=FONT_CHOICES,
                           groups=THEME_GROUPS, shadow_presets=SHADOW_PRESETS,
                           values=theme_values(), css=theme_css(),
                           **_shell(store))


@bp.post("/admin/theme")
@roles_required("super_admin", "franchise_owner")
def theme_save():
    changed = 0
    for key, _label, _prop, _kind, _default, _help, _group in THEME_TOKENS:
        val = (request.form.get(key) or "").strip()
        row = SiteSetting.query.filter_by(key=key).first()
        # An empty box means "use the built-in value", so the row is removed
        # rather than stored blank | that keeps theme_css() free of noise.
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
# style vocabulary works there | this is the UI for it.
from app.models.page import INNER_PAGES, INNER_PAGE_BY_KEY, inner_sections  # noqa: E402

# ── Retired: one control that moved several unrelated things ────────────
# These keys are still understood by pb_section_style(), so a section saved
# before this change renders exactly as it did. They are no longer offered
# anywhere, because each of them reached more than one kind of text at once |
# "Heading size" set the section heading, the card headings at 70% and the
# sub-headings at 58%, so sizing a hero heading moved the line underneath it.
# Every one of them now has a per-element equivalent that moves one thing:
#   style_hcolor  -> Main heading / Card heading -- Colour
#   style_font    -> Main heading / Card heading -- Font
#   style_hweight -> ... -- Weight        style_case    -> ... -- Capitals
#   style_hsize   -> ... -- Size          style_hlh     -> ... -- Line height
#   style_tracking-> ... -- Letter spacing  style_italic -> ... -- Slant
#   style_tcolor  -> Paragraph text -- Colour   style_lh   -> ... -- Line height
#   style_bsize   -> Paragraph / Card text / Sub heading -- Size
#   style_bweight -> Paragraph text -- Weight
#   style_bodyfont-> Paragraph / Card text / Label / Button / Caption -- Font
#   style_textw   -> each element's own Text width
#   style_btnbg/btntext/btnradius/btnborder -> Button states -- Normal
RETIRED_STYLE_FIELDS = [
    "style_hcolor", "style_tcolor", "style_font", "style_bodyfont",
    "style_hweight", "style_case", "style_hsize", "style_tracking",
    "style_lh", "style_textw", "style_bweight", "style_bsize",
    "style_italic", "style_hlh",
    "style_btnbg", "style_btntext", "style_btnradius", "style_btnborder",
    # one shadow for every h1-h6, p, li, span and link in the section; each
    # kind of text has its own four now (TEXT_ROLE_PROP_SPECS)
    "style_tsside", "style_tsdist", "style_tsblur", "style_tscolor",
]

# key, label, input type | matches what pb_section_style() understands
DESIGN_FIELDS = [
    ("style_bg", "Section background", "color"),
    ("style_accent", "Accent colour", "color"),
    ("style_align", "Text alignment", "align"),
    ("style_shadow", "Card shadow", "shadow"),
    ("style_imgoverlay", "Image overlay", "color"),
    ("style_imgradius", "Image corner radius", "px"),
    ("style_divider", "Divider line", "color"),
    ("style_bgimage", "Section background picture", "image"),
    ("style_bgsize", "How it sits", "bgsize"),
    ("style_bgpos", "Where it sits", "bgpos"),
    ("style_gradfrom", "Gradient from", "color"),
    ("style_gradto", "Gradient to", "color"),
    ("style_graddir", "Gradient direction", "graddir"),
    ("style_imgfilter", "Photo effect", "filter"),
    ("style_link", "Link colour", "color"),
    ("style_cardpad", "Card padding", "px"),
    ("style_cardborderw", "Card border width", "px"),
    ("style_cardw", "Card width", "px"),
    ("style_cardh", "Card minimum height", "px"),
    ("style_minh", "Minimum height", "px"),
    ("style_px", "Side padding", "px"),
    ("style_valign", "Vertical position", "valign"),
    ("style_imgh", "Picture height", "px"),
    ("style_imgfit", "Picture fit", "imgfit"),
    ("style_cardcols", "Cards per row", "cols"),
    ("style_cardminw", "Card minimum width", "px"),
    ("style_gap", "Gap between items", "px"),
    ("style_squigcolor", "Squiggle colour", "color"),
    ("style_squigw", "Squiggle width", "px"),
    ("style_navlink", "Nav link colour", "color"),
    ("style_iconcolor", "Icon colour", "color"),
    ("style_logoh", "Logo height", "px"),
    ("style_xtraimg", "Extra picture", "image"),
    ("style_xtrapos", "Where it goes", "xtrapos"),
    ("style_xtraw", "Its width", "px"),
    ("style_xtrah", "Its height", "px"),
    ("style_xtraradius", "Its corners", "px"),
    ("style_xtraborder", "Its border colour", "color"),
    ("style_xtraborderw", "Its border width", "px"),
    ("style_xtrashadow", "Its shadow", "shadow"),
    ("style_xtraalign", "Its position", "xtraalign"),
    ("style_maxw", "Content width", "px"),
    ("style_pt", "Padding top", "px"),
    ("style_pb", "Padding bottom", "px"),
    ("style_cardbg", "Card background", "color"),
    ("style_cardborder", "Card border", "color"),
    ("style_cardhead", "Card heading", "color"),
    ("style_cardtext", "Card text", "color"),
    ("style_cardradius", "Card radius", "px"),
    ("style_overlay", "Image overlay", "opacity"),
]


# ── Per-role typography ─────────────────────────────────────────────────
# One set of controls per KIND of text, so restyling a heading cannot reach the
# sub-heading, the body copy, the card titles or the button labels. The roles
# and the properties are the same list the CSS and pb_section_style() use.
TEXT_ROLE_LABELS = [
    ("title", "Main heading"),
    ("titlehl", "Highlighted words"),
    ("sub", "Sub heading"),
    ("body", "Paragraph text"),
    ("eyebrow", "Label / badge"),
    ("cardtitle", "Card heading"),
    ("cardtext", "Card text"),
    ("btn", "Button text"),
    ("nav", "Navigation link"),
    ("meta", "Price / caption"),
]

TEXT_ROLE_PROP_SPECS = [
    ("family", "Font", "font"),
    ("size", "Size (px)", "px"),
    ("sizemd", "Size from 768px", "px"),
    ("sizelg", "Size from 1024px", "px"),
    ("weight", "Weight", "weight"),
    ("lh", "Line height", "ratio"),
    ("track", "Letter spacing", "pxfine"),
    ("case", "Capitals", "case"),
    ("italic", "Slant", "italic"),
    ("color", "Colour", "color"),
    ("maxw", "Text width (px)", "pxwide"),
    ("align", "Alignment", "align"),
    ("mt", "Space above (px)", "px"),
    ("mb", "Space below (px)", "px"),
    # composed into one --pb-<role>-shadow by pb_section_style
    ("tsside", "Shadow | which side", "tsside"),
    ("tsdist", "Shadow | how far (px)", "px"),
    ("tsblur", "Shadow | how soft (px)", "px"),
    ("tscolor", "Shadow | colour", "color"),
]
# Tablet (md) / desktop (lg) copies | size already has sizemd/sizelg.
TEXT_ROLE_PROP_SPECS = TEXT_ROLE_PROP_SPECS + [
    (prop + bp, "%s (%s)" % (label, "tablet" if bp == "md" else "desktop"), kind)
    for prop, label, kind in TEXT_ROLE_PROP_SPECS
    if prop not in ("size", "sizemd", "sizelg")
    for bp in ("md", "lg")
]

TEXT_ROLE_FIELDS = [
    ("style_%s_%s" % (role, prop), "%s | %s" % (role_label, prop_label), kind)
    for role, role_label in TEXT_ROLE_LABELS
    for prop, prop_label, kind in TEXT_ROLE_PROP_SPECS
]

TEXT_ROLE_KEYS = {f[0] for f in TEXT_ROLE_FIELDS}

TEXT_ROLE_FIELDS_BY_ROLE = {
    role: [("style_%s_%s" % (role, prop), prop_label, kind)
           for prop, prop_label, kind in TEXT_ROLE_PROP_SPECS]
    for role, _label in TEXT_ROLE_LABELS
}


# ── Button states ───────────────────────────────────────────────────────
# Each state holds its own colours. Nothing is derived: a hover background does
# not imply a hover label colour, which is how a label ends up invisible against
# the fill behind it.
CTA_STATE_LABELS = [
    ("default", "Normal"),
    ("hover", "Hover"),
    ("focus", "Keyboard focus"),
    ("active", "Being pressed"),
    ("disabled", "Disabled"),
]

CTA_PROP_SPECS = [
    ("bg", "Background", "color"),
    ("text", "Text", "color"),
    ("border", "Border", "color"),
    ("borderw", "Border width (px)", "px"),
    ("icon", "Icon", "color"),
    ("shadow", "Shadow", "shadow"),
    ("opacity", "Opacity", "opacity"),
    ("weight", "Weight", "weight"),
    ("decoration", "Underline", "decoration"),
    ("lift", "Lift (px)", "pxfine"),
    ("scale", "Scale", "ratio"),
    ("radius", "Corners (px)", "px"),
]

CTA_FIELDS = [
    ("style_cta_%s_%s" % (state, prop), "%s | %s" % (state_label, prop_label), kind)
    for state, state_label in CTA_STATE_LABELS
    for prop, prop_label, kind in CTA_PROP_SPECS
] + [
    ("style_cta_focusring", "Focus ring colour", "color"),
    ("style_cta_dur", "Transition (seconds)", "seconds"),
]

CTA_KEYS = {f[0] for f in CTA_FIELDS}

CTA_FIELDS_BY_STATE = {
    state: [("style_cta_%s_%s" % (state, prop), prop_label, kind)
            for prop, prop_label, kind in CTA_PROP_SPECS]
    for state, _label in CTA_STATE_LABELS
}

DECORATION_CHOICES = [("", "Default"), ("none", "None"), ("underline", "Underline"),
                      ("line-through", "Strikethrough")]


@bp.get("/admin/design")
@roles_required(*ADMIN_ROLES)
def design():
    store = _admin_store()
    page = request.args.get("page") or INNER_PAGES[0]["page"]
    # "site" is not a page | it is the copy that belongs to no single page
    # (the footer, and text shared by Deals / Rewards / Gift cards). It used to
    # live on its own tab, which meant every page's words appeared twice.
    if page == "site":
        page_urls = {p["url"] for p in INNER_PAGES} | {"/"}
        groups = [g for g in PAGE_CONTENT if g.get("url") not in page_urls
                  or g["key"] in ("footer", "storefront")]
        current = {r.key: r.value for r in SiteSetting.query.all() if r.value}
        defaults = page_content_defaults(current_app.config.get("BRAND_NAME", ""))
        return render_template("admin/design.html",
                               pages=INNER_PAGES, page=page,
                               spec={"label": "Footer & shared text", "url": "/"},
                               sections=[], fields=DESIGN_FIELDS, inuse={},
                               role_groups=TEXT_ROLE_LABELS,
                               role_fields_by_role=TEXT_ROLE_FIELDS_BY_ROLE,
                               cta_states=CTA_STATE_LABELS,
                               cta_fields_by_state=CTA_FIELDS_BY_STATE,
                               decorations=DECORATION_CHOICES,
                               fonts=CANVAS_FONT_CHOICES, weights=CANVAS_WEIGHTS,
                               cases=CANVAS_CASES, styled={},
                               text_groups=groups, content_current=current,
                               content_defaults=defaults, **_shell(store))
    spec = INNER_PAGE_BY_KEY.get(page)
    if not spec:
        abort(404)
    _secs = inner_sections(page)
    styled = {s["key"]: any(str(v).strip() for k, v in s["config"].items()
                            if k.startswith("style_"))
              for s in _secs}
    # how many settings each section actually overrides, so the screen can say
    # so and the admin is not hunting through a hundred "default" boxes
    inuse = {s["key"]: sum(1 for k, v in s["config"].items()
                           if k.startswith("style_") and str(v).strip())
             for s in _secs}
    # The words on this page live in the same screen as its design now | a
    # client editing the Contact page should not have to work out that the
    # heading is on one tab and the section colour on another.
    current = {r.key: r.value for r in SiteSetting.query.all() if r.value}
    defaults = page_content_defaults(current_app.config.get("BRAND_NAME", ""))
    text_groups = [g for g in PAGE_CONTENT
                   if g.get("url") == spec["url"] and g["key"] not in ("footer", "storefront")]
    return render_template("admin/design.html",
                           pages=INNER_PAGES, page=page, spec=spec,
                           sections=_secs, fields=DESIGN_FIELDS, inuse=inuse,
                           role_groups=TEXT_ROLE_LABELS,
                           role_fields_by_role=TEXT_ROLE_FIELDS_BY_ROLE,
                           cta_states=CTA_STATE_LABELS,
                           cta_fields_by_state=CTA_FIELDS_BY_STATE,
                           decorations=DECORATION_CHOICES,
                           fonts=CANVAS_FONT_CHOICES, weights=CANVAS_WEIGHTS, cases=CANVAS_CASES, shadows=SHADOW_CHOICES,
                           tssides=TSSIDE_CHOICES, italics=ITALIC_CHOICES,
                           bgsizes=BGSIZE_CHOICES, bgposes=BGPOS_CHOICES,
                           graddirs=GRADDIR_CHOICES, filters=FILTER_CHOICES,
                           valigns=VALIGN_CHOICES, imgfits=IMGFIT_CHOICES, colss=COLS_CHOICES,
                           xtraposes=XTRAPOS_CHOICES, xtraaligns=XTRAALIGN_CHOICES,
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
    for fkey, _label, _kind in DESIGN_FIELDS + TEXT_ROLE_FIELDS + CTA_FIELDS:
        val = (request.form.get(fkey) or "").strip()
        # blank clears the override rather than storing "" | keeps the inline
        # style attribute (and therefore the CSS) free of dead declarations
        if val and not style_value_ok(val):
            flash("%s was left alone: that is not a valid value." % _label, "error")
        elif val:
            cfg[fkey] = val
        else:
            cfg.pop(fkey, None)
    # an uploaded backdrop wins over whatever is in the link box
    up = _save_image(request.files.get("style_bgimage_file"), "sec-%s-%s" % (page, key))
    if up:
        cfg["style_bgimage"] = up
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

    # Only keys the Page Content registry knows about | this endpoint must not
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
