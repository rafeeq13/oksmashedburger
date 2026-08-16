"""Application factory — OK Smashed Burger platform (modular monolith)."""
import os
import re

from flask import Flask, render_template, request, session, g

from .config import get_config
from .extensions import db, migrate, jwt, limiter

# a plain number, with no unit stuck on the end of it yet
_BARE_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")

# The kinds of text a section can hold. Each one owns its typography outright:
# the selectors in builder.css are mutually exclusive, so a change to one role
# cannot reach another. Keep this list and that file in step.
TEXT_ROLES = ("title", "titlehl", "sub", "body", "eyebrow", "cardtitle",
              "cardtext", "btn", "nav", "meta")

# property key -> unit appended when the saved value is a bare number.
# `sizemd` is from 768px up and `sizelg` from 1024px, matching the breakpoints
# the stylesheets already use, so responsive type stays on the same grid.
TEXT_ROLE_PROPS = (("family", ""), ("color", ""), ("size", "px"),
                   ("sizemd", "px"), ("sizelg", "px"), ("weight", ""),
                   ("lh", ""), ("track", "px"), ("case", ""), ("italic", ""),
                   ("align", ""), ("maxw", "px"), ("mt", "px"), ("mb", "px"))

# A button's five states, each holding its own colours and geometry. Nothing is
# derived from anything else: the hover fill never implies a hover label colour,
# which is exactly how a label ends up the same colour as the fill behind it.
CTA_STATES = ("default", "hover", "focus", "active", "disabled")

CTA_PROPS = (("bg", ""), ("text", ""), ("border", ""), ("borderw", "px"),
             ("icon", ""), ("shadow", ""), ("opacity", ""), ("weight", ""),
             ("decoration", ""), ("lift", "px"), ("scale", ""), ("radius", "px"))

# not tied to a state: the focus ring's colour, and the shared timing
CTA_EXTRA_PROPS = (("focus-ring", ""), ("dur", "s"), ("ease", ""))


def create_app(config_object=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_object or get_config())

    # ── Extensions ──────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    from .security import init_csrf
    init_csrf(app)

    # ── Models (import so metadata is registered) ───────────────
    from . import models  # noqa: F401

    # ── Blueprints (one per domain, per SRS §3.2) ───────────────
    from .blueprints.website import bp as website_bp
    from .blueprints.stores import bp as stores_bp
    from .blueprints.menu import bp as menu_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.account import bp as account_bp
    from .blueprints.cart import bp as cart_bp
    from .blueprints.checkout import bp as checkout_bp
    from .blueprints.tracking import bp as tracking_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.driver import bp as driver_bp
    app.register_blueprint(website_bp)
    app.register_blueprint(stores_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(driver_bp)

    # ── Feature switches: the page itself, not just the link ────────────
    # Hiding a nav entry is cosmetic — the URL still works, and a search
    # engine or an old bookmark walks straight in. A switched-off area is
    # gone from the routing table's point of view too.
    FEATURE_PATHS = [
        ("/deals", "deals"),
        ("/rewards", "rewards"),
        ("/gift-cards", "giftcards"),
        ("/giftcards", "giftcards"),
        ("/news", "news"),
    ]

    @app.before_request
    def _feature_gate():
        from flask import request, abort
        path = request.path.rstrip("/") or "/"
        if path.startswith("/admin"):
            return None                     # the admin can always reach its own screens
        for prefix, feat in FEATURE_PATHS:
            if path == prefix or path.startswith(prefix + "/"):
                from .models.site import SiteSetting, features_from
                rows = {r.key: r.value for r in SiteSetting.query.all() if r.value}
                if not features_from(rows).get(feat, True):
                    abort(404)
                break
        return None

    # ── Static assets: cache hard, bust on change ────────────────────────
    # Nothing was setting a cache policy, so every visit re-fetched ~360 KB of
    # CSS/JS. A one-year max-age is only safe with a busting token, so
    # url_for('static', …) gets ?v=<mtime> appended automatically — the URL
    # changes the moment a file is edited and browsers pick it up immediately.
    # Assigned, not setdefault: Flask ships this key pre-set to None, so
    # setdefault would silently leave caching off.
    if app.config.get("SEND_FILE_MAX_AGE_DEFAULT") is None:
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000

    _static_versions = {}

    @app.url_defaults
    def _stamp_static(endpoint, values):
        if endpoint != "static" or "filename" not in values:
            return
        name = values["filename"]
        stamp = _static_versions.get(name)
        if stamp is None or app.debug:
            try:
                stamp = int(os.stat(os.path.join(app.static_folder, name)).st_mtime)
            except OSError:
                stamp = 0
            _static_versions[name] = stamp
        if stamp:
            values["v"] = stamp

    @app.after_request
    def _security_headers(resp):
        """Baseline hardening. Deliberately no CSP — the site and the page
        builder both emit inline styles/scripts, so a policy strict enough to
        matter would break them; that needs its own pass with nonces."""
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy",
                                "geolocation=(self), camera=(), microphone=()")
        # Never serve an admin screen or the on-page editor from cache. The
        # editor's code is inlined into the page, so a tab left open across an
        # update keeps running the old one: its controls can write settings the
        # site has since dropped, and the change looks applied until a reload
        # throws it away. no-store also keeps the back button from restoring
        # such a page from the browser's history cache.
        path = request.path or ""
        if path.startswith("/admin") or request.args.get("edit") or request.args.get("pbedit"):
            resp.headers["Cache-Control"] = "no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
        return resp

    # ── Template context: header/footer need current store, nav, cart, user ──
    from .models.store import Store
    from .auth import current_user
    from .security import get_csrf_token, style_value_ok

    def pb_section_style(cfg):
        """Inline CSS (vars + props) for a page-builder section wrapper, built
        from its style_* config. Paired with the .pb-sec rules in style.css."""
        cfg = cfg or {}
        parts = []

        def put(var, value):
            """One declaration — but only if the value is really just a value.

            Everything here ends up inside a style attribute the whole internet
            reads, and inside the editor's own panel afterwards. A value holding
            a semicolon or a quote would stop being a value and start being
            extra CSS, so it is dropped rather than emitted. Settings already
            saved are covered too, which is why the check lives here as well as
            at the two save routes."""
            if style_value_ok(value):
                parts.append("%s:%s" % (var, value))

        for k, var in (("style_bg", "--pb-bg"), ("style_hcolor", "--pb-hcolor"),
                       ("style_tcolor", "--pb-tcolor"), ("style_font", "--pb-font"),
                       ("style_overlay", "--pb-overlay"),
                       # card-level styling (Visual Editor "Cards" controls)
                       ("style_cardbg", "--pb-cardbg"), ("style_cardborder", "--pb-cardborder"),
                       ("style_cardhead", "--pb-cardhead"), ("style_cardtext", "--pb-cardtext"),
                       # typography beyond the heading font
                       ("style_bodyfont", "--pb-bodyfont"), ("style_hweight", "--pb-hweight"),
                       ("style_case", "--pb-case"), ("style_lh", "--pb-lh"),
                       # accent, overlay tint and button colours
                       ("style_accent", "--pb-accent"),
                       ("style_overlaycolor", "--pb-overlaycolor"),
                       ("style_btnbg", "--pb-btnbg"), ("style_btntext", "--pb-btntext"),
                       ("style_shadow", "--pb-shadow"),
                       # text shadow, image treatment, body type, dividers
                       ("style_imgoverlay", "--pb-imgoverlay"),
                       ("style_bweight", "--pb-bweight"),
                       ("style_italic", "--pb-italic"),
                       ("style_divider", "--pb-divider"),
                       # a section's own backdrop: picture, how it sits, a
                       # gradient wash over it, and what happens to photos
                       ("style_bgsize", "--pb-bgsize"), ("style_bgpos", "--pb-bgpos"),
                       ("style_bgrepeat", "--pb-bgrepeat"),
                       ("style_gradfrom", "--pb-gradfrom"), ("style_gradto", "--pb-gradto"),
                       ("style_graddir", "--pb-graddir"),
                       ("style_imgfilter", "--pb-imgfilter"),
                       ("style_link", "--pb-link"), ("style_valign", "--pb-valign"),
                       ("style_btnborder", "--pb-btnborder"),
                       # header / footer chrome, and the brand squiggle
                       ("style_navlink", "--pb-navlink"), ("style_iconcolor", "--pb-iconcolor"),
                       ("style_squigcolor", "--pb-squigcolor"),
                       ("style_imgfit", "--pb-imgfit"), ("style_cardcols", "--pb-cardcols"),
                       # an extra picture the client drops into a section
                       ("style_xtraborder", "--pb-xtraborder"),
                       ("style_xtrashadow", "--pb-xtrashadow"),
                       ("style_xtraalign", "--pb-xtraalign")):
            if cfg.get(k) not in (None, ""):
                put(var, cfg[k])
        # the ones that carry a unit
        for k, var, unit in (("style_cardradius", "--pb-cardradius", "px"),
                             ("style_btnradius", "--pb-btnradius", "px"),
                             ("style_tracking", "--pb-tracking", "px"),
                             ("style_hsize", "--pb-hsize", "px"),
                             ("style_maxw", "--pb-maxw", "px"),
                             ("style_imgradius", "--pb-imgradius", "px"),
                             ("style_bsize", "--pb-bsize", "px"),
                             ("style_hlh", "--pb-hlh", ""),
                             ("style_cardpad", "--pb-cardpad", "px"),
                             ("style_cardborderw", "--pb-cardborderw", "px"),
                             ("style_cardw", "--pb-cardw", "px"),
                             ("style_cardh", "--pb-cardh", "px"),
                             ("style_textw", "--pb-textw", "px"),
                             ("style_minh", "--pb-minh", "px"),
                             ("style_px", "--pb-px", "px"),
                             ("style_logoh", "--pb-logoh", "px"),
                             ("style_squigw", "--pb-squigw", "px"),
                             # sizing: how tall a picture is, how wide a card
                             # column gets, and the gap between cards
                             ("style_imgh", "--pb-imgh", "px"),
                             ("style_cardminw", "--pb-cardminw", "px"),
                             ("style_gap", "--pb-gap", "px"),
                             ("style_xtraw", "--pb-xtraw", "px"),
                             ("style_xtrah", "--pb-xtrah", "px"),
                             ("style_xtraradius", "--pb-xtraradius", "px"),
                             ("style_xtraborderw", "--pb-xtraborderw", "px")):
            if cfg.get(k) not in (None, ""):
                # Two things write these keys: Page design saves a bare number,
                # the on-page panel saves the number with its unit already on
                # it. Appending blindly produced "28pxpx", which the browser
                # throws away — the control looked like it did nothing after a
                # reload. Only add the unit when the value is still just a
                # number.
                raw = str(cfg[k]).strip()
                put(var, raw + unit if _BARE_NUMBER.match(raw) else raw)
        # ── per-role typography ────────────────────────────────────
        # Every kind of text in a section carries its own settings, so restyling
        # a heading can no longer drag the sub-heading, the body copy, the card
        # titles or the button labels along with it. A role's rule in
        # builder.css only exists while its variable is here, so a section that
        # was styled before any of this looks exactly as it did.
        for role in TEXT_ROLES:
            for prop, unit in TEXT_ROLE_PROPS:
                raw = str(cfg.get("style_%s_%s" % (role, prop), "") or "").strip()
                if not raw:
                    continue
                put("--pb-%s-%s" % (role, prop),
                    raw + unit if (unit and _BARE_NUMBER.match(raw)) else raw)
        # ── button states ──────────────────────────────────────────
        for state in CTA_STATES:
            for prop, unit in CTA_PROPS:
                raw = str(cfg.get("style_cta_%s_%s" % (state, prop), "") or "").strip()
                if not raw:
                    continue
                put("--pb-cta-%s-%s" % (state, prop),
                    raw + unit if (unit and _BARE_NUMBER.match(raw)) else raw)
        for prop, unit in CTA_EXTRA_PROPS:
            raw = str(cfg.get("style_cta_%s" % prop.replace("-", ""), "") or "").strip()
            if not raw:
                continue
            put("--pb-cta-%s" % prop,
                raw + unit if (unit and _BARE_NUMBER.match(raw)) else raw)
        # ── text shadow, composed ──────────────────────────────────
        # Four controls make one value, which is why this is built here rather
        # than emitted like the others. "none" has to emit something: several
        # sections carry a built-in shadow (the home hero stacks four of them),
        # and saying nothing left that shadow in place, so choosing No shadow
        # appeared to do nothing at all.
        def compose_shadow(prefix):
            side = (cfg.get(prefix + "tsside") or "").strip()
            if side == "none":
                return "none"
            if not side:
                return ""
            try:
                dist = int(float(cfg.get(prefix + "tsdist") or 2))
            except (TypeError, ValueError):
                dist = 2
            try:
                blur = int(float(cfg.get(prefix + "tsblur") or 4))
            except (TypeError, ValueError):
                blur = 4
            col = (cfg.get(prefix + "tscolor") or "rgba(0,0,0,.5)").strip()
            offsets = {
                "top":    [(0, -dist)],
                "bottom": [(0, dist)],
                "left":   [(-dist, 0)],
                "right":  [(dist, 0)],
                "all":    [(0, -dist), (0, dist), (-dist, 0), (dist, 0)],
            }.get(side, [(0, dist)])
            return ", ".join("%dpx %dpx %dpx %s" % (x, y, blur, col) for x, y in offsets)

        # the older section-wide one, for anything saved before shadows became
        # per-element; it is not offered anywhere now
        old_shadow = compose_shadow("style_")
        if old_shadow:
            put("--pb-textshadow", old_shadow)
        # and one per kind of text, so a shadow on the heading is not a shadow
        # on the line underneath it
        for role in TEXT_ROLES:
            value = compose_shadow("style_%s_" % role)
            if value:
                put("--pb-%s-shadow" % role, value)

        if cfg.get("style_bgimage") not in (None, ""):
            # strip the edit-mode tag so it never lands in the saved CSS
            _u = str(cfg["style_bgimage"]).split("#ie=")[0]
            put("--pb-bgimage", "url('%s')" % _u.replace("'", "%27"))
        if cfg.get("style_xtraimg") not in (None, ""):
            _x = str(cfg["style_xtraimg"]).split("#ie=")[0]
            put("--pb-xtraimg", "url('%s')" % _x.replace("'", "%27"))
            # Above or below the section. This was never emitted at all, so
            # "Where it goes" was a control with nothing on the other end of
            # it; the picture sits in the section's flex order, so above is
            # simply an order before the section's own.
            if (cfg.get("style_xtrapos") or "").strip() == "top":
                put("--pb-xtraorder", "0")
        if cfg.get("style_pt") not in (None, ""):
            put("padding-top", "%spx" % cfg["style_pt"])
        if cfg.get("style_pb") not in (None, ""):
            put("padding-bottom", "%spx" % cfg["style_pb"])
        if cfg.get("style_align"):
            put("text-align", cfg["style_align"])
        return ";".join(parts)

    app.jinja_env.globals["pb_section_style"] = pb_section_style

    def pb_cfg(key, cfg):
        """Section config, with its words already editable when ?edit=1."""
        from .blueprints.website import _editable_cfg
        try:
            return _editable_cfg(key, cfg)
        except Exception:
            return cfg or {}

    app.jinja_env.globals["pb_cfg"] = pb_cfg

    def _style_rows():
        """Every saved section style that can apply to the page being rendered.

        Fetched once per request: the <head> asks it what fonts to fetch and
        whether the per-element stylesheet is needed, and both questions have
        the same answer source.
        """
        rows = getattr(g, "_pb_style_rows", None)
        if rows is not None:
            return rows
        from .models.page import PageSection, INNER_PAGES
        path = (request.path or "/").rstrip("/") or "/"
        page_key = "home" if path == "/" else next(
            (p["page"] for p in INNER_PAGES if p["url"].rstrip("/") == path), None)
        # the page's own sections, plus the shared chrome — a face picked for the
        # header or the footer belongs to every page — plus the builder page's
        # own key when one is being rendered
        wanted = ["site"] + ([page_key] if page_key else [])
        builder_key = getattr(g, "pb_builder_key", None)
        if builder_key:
            wanted.append(builder_key)
        try:
            rows = PageSection.query.filter(PageSection.page.in_(wanted)).all()
        except Exception:
            rows = []                  # a missing table must not break the page
        g._pb_style_rows = rows
        return rows

    app.jinja_env.globals["pb_style_rows"] = _style_rows

    def pb_parts_css():
        """Does this page need the per-element typography stylesheet?

        It is 190 KB of selectors that anchor on p, a, span, div and h1-h6, and
        it can only ever do something on a page that has actually set one of its
        variables — which today is almost none of them. Asking for it only when
        it can matter keeps that weight off every ordinary visitor, while the
        editor always gets it because it writes those variables live.
        """
        if request.args.get("edit") or request.args.get("pbedit"):
            return True
        role_prefixes = tuple("style_%s_" % r for r in TEXT_ROLES)
        for row in _style_rows():
            for key in (row.config or {}):
                if key.startswith("style_cta_") or key.startswith(role_prefixes):
                    return True
        return False

    app.jinja_env.globals["pb_parts_css"] = pb_parts_css

    def google_fonts_link():
        """<link> for the webfonts this site's sections actually ask for.

        The designer offers 160 families; fetching them all would cost far more
        than the whole stylesheet, so a page asks only for the faces its own
        sections actually chose. The three brand faces are always included
        because the base design uses them.
        """
        from .models.site import SiteSetting  # noqa: F401  (kept for symmetry)
        from .blueprints.admin import CANVAS_FONTS
        from .fonts import GOOGLE_SPEC

        # the whole library, with the older short list as a fallback for any
        # stack that predates it
        by_stack = dict(GOOGLE_SPEC)
        by_stack.update({f[0]: f[2] for f in CANVAS_FONTS if f[2]})
        wanted = {"Quicksand:wght@400;500;600;700",
                  "Poppins:wght@400;500;600;700;800;900",
                  "Inter:wght@300;400;500;600;700;800"}
        try:
            # only what can apply to this page — otherwise a face picked for
            # Contact would be downloaded on the home page too, for nothing
            # every place a face can be chosen: the two older section-wide keys
            # and the per-element ones
            font_keys = ["style_font", "style_bodyfont"] + [
                "style_%s_family" % role for role in TEXT_ROLES]
            for row in _style_rows():
                cfg = row.config or {}
                for key in font_keys:
                    fam = by_stack.get(cfg.get(key) or "")
                    if fam:
                        wanted.add(fam)
        except Exception:
            pass                       # a missing table must not break the page
        q = "&".join("family=" + f for f in sorted(wanted))
        return ("https://fonts.googleapis.com/css2?" + q + "&display=swap")

    app.jinja_env.globals["google_fonts_link"] = google_fonts_link

    def pb_page_style(page, key):
        """Inline style for an inner-page section. Same contract as
        pb_section_style, just looked up by (page, key) instead of being
        handed a config — the templates have no row object to pass."""
        from .models.page import inner_section_config
        try:
            return pb_section_style(inner_section_config(page, key))
        except Exception:
            return ""

    app.jinja_env.globals["pb_page_style"] = pb_page_style

    def pb_btn_style(cfg):
        cfg = cfg or {}
        sz = cfg.get("btn_size")
        if sz == "sm":
            return "font-size:.8rem;padding:.45rem 1rem"
        if sz == "lg":
            return "font-size:1.05rem;padding:.9rem 1.75rem"
        return ""

    def pb_btnwrap_style(cfg):
        cfg = cfg or {}
        a = cfg.get("btn_align")
        return ("text-align:" + a) if a else ""

    def pb_img_style(cfg):
        cfg = cfg or {}
        parts = []
        if cfg.get("img_w"):
            parts.append("width:%s%%" % cfg["img_w"])
        a = cfg.get("img_align")
        if a == "center":
            parts.append("margin-left:auto;margin-right:auto")
        elif a == "right":
            parts.append("margin-left:auto;margin-right:0")
        elif a == "left":
            parts.append("margin-left:0;margin-right:auto")
        if parts:
            parts.append("display:block")
        return ";".join(parts)

    app.jinja_env.globals["pb_btn_style"] = pb_btn_style
    app.jinja_env.globals["pb_btnwrap_style"] = pb_btnwrap_style
    app.jinja_env.globals["pb_img_style"] = pb_img_style

    # Admin-editable content lists (hero slides, reviews, jobs, news, FAQ…).
    # Falls back to the built-in defaults until the client imports a list.
    from .models.content import content_list, testimonials_feed, tier_status
    app.jinja_env.globals["content_list"] = content_list

    # Client-editable brand palette / type / radius (Admin > Theme).
    from .models.theme import theme_css
    app.jinja_env.globals["theme_css"] = theme_css

    @app.template_filter("nice_when")
    def nice_when(value):
        """"2026-08-09T14:45" -> "Today at 2:45 PM". The raw ISO string was
        being printed straight onto the store card."""
        from datetime import datetime, timedelta
        try:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except (TypeError, ValueError):
            return value or ""
        today = datetime.now().date()
        if dt.date() == today:
            day = "Today"
        elif dt.date() == today + timedelta(days=1):
            day = "Tomorrow"
        else:
            day = dt.strftime("%a %b %d")
        return "%s at %s" % (day, dt.strftime("%I:%M %p").lstrip("0"))
    app.jinja_env.globals["testimonials_feed"] = testimonials_feed
    app.jinja_env.globals["tier_status"] = tier_status

    @app.context_processor
    def inject_globals():
        stores = Store.query.filter_by(is_active=True).order_by(Store.name).all()
        current = None
        slug = session.get("store_slug")
        if slug:
            current = next((s for s in stores if s.slug == slug), None)
        if current is None and stores:
            current = stores[0]
        user = current_user()
        favorite_ids = {f.product_id for f in user.favorites} if user else set()
        from .models.site import SiteSetting, SITE_IMAGE_DEFAULTS, features_from
        from .blueprints.admin import (CANVAS_FONT_CHOICES, CANVAS_WEIGHTS,
                                       CANVAS_CASES, SHADOW_CHOICES,
                                       TSSIDE_CHOICES, ITALIC_CHOICES,
                                       BGSIZE_CHOICES, BGPOS_CHOICES,
                                       GRADDIR_CHOICES, FILTER_CHOICES,
                                       VALIGN_CHOICES, IMGFIT_CHOICES,
                                       COLS_CHOICES, XTRAPOS_CHOICES,
                                       XTRAALIGN_CHOICES, FONT_PICKER,
                                       FONT_CATEGORIES, FONT_GOOGLE_SPEC,
                                       RETIRED_STYLE_FIELDS)
        from .models.page import BuilderPage, page_content_defaults
        site = {s.key: s.value for s in SiteSetting.query.all() if s.value}

        class _Marked(dict):
            """In edit mode, hand back the URL with the slot key tagged on.

            Every picture on the site comes out of one of these two dicts, so
            tagging them here means the on-page editor can identify any image
            without a single template being touched. The tag is a URL fragment,
            which a browser ignores when it fetches the image.
            """
            def get(self, key, default=None):
                val = dict.get(self, key, default)
                if val and isinstance(val, str) and (key.endswith("_img")
                                                     or key.startswith("brand_")
                                                     or key.endswith("_poster")):
                    return "%s#ie=%s" % (val, key)
                return val

        # Admin-editable page copy. Templates call pc('key') instead of
        # repeating the default inline: the default then lives ONLY in
        # PAGE_CONTENT, so the admin screen can never pre-fill text that is not
        # what the page actually shows (About's had drifted on 5 of 6 fields).
        pc_defaults = page_content_defaults(app.config["BRAND_NAME"])

        def pc_attr(key, fallback=""):
            """Plain string — for use inside an HTML attribute, where a
            wrapper element would corrupt the markup."""
            return site.get(key) or pc_defaults.get(key) or fallback

        # Inline editing: an admin visiting any page with ?edit=1 gets every
        # pc() string wrapped in a tagged span, which the editor turns into a
        # contenteditable. Ordinary visitors get the bare string, so the public
        # HTML is byte-identical to before.
        _u = current_user()
        _inline = (bool(request.args.get("edit"))
                   and _u is not None and _u.role is not None
                   and _u.role.name in ("super_admin", "franchise_owner", "store_manager"))

        def pc(key, fallback=""):
            val = site.get(key) or pc_defaults.get(key) or fallback
            if not _inline:
                return val
            from markupsafe import Markup, escape
            return Markup('<span class="ok-ie" data-pc="%s" title="Click to edit">%s</span>'
                          % (escape(key), escape(val)))
        # Parts of the site the client has switched off disappear from every
        # menu here, so no template has to remember to check.
        feats = features_from(site)
        more_children = [
            {"label": "Rewards", "href": "/rewards", "feature": "rewards"},
            {"label": "Gift Cards", "href": "/gift-cards", "feature": "giftcards"},
            {"label": "Contact", "href": "/contact"},
            {"label": "Join Our Team", "href": "/careers"},
            {"label": "News", "href": "/news", "feature": "news"},
        ]
        more_children = [c for c in more_children if feats.get(c.get("feature"), True)]
        for p in BuilderPage.query.filter_by(show_in_nav=True, published=True).order_by(BuilderPage.title).all():
            more_children.append({"label": p.title, "href": "/p/" + p.slug})
        # Brand artwork is admin-set with the shipped file as the fallback, so
        # the logo is not something only a developer can change.
        from flask import url_for as _url_for
        def _asset(key, fallback):
            return site.get(key) or _url_for("static", filename=fallback)

        return {
            "brand_name": app.config["BRAND_NAME"],
            "logo_url": _asset("brand_logo", "img/logo.png"),
            "favicon_url": _asset("brand_favicon", "img/favicon.ico"),
            "app_icon_url": _asset("brand_app_icon", "img/logo-icon.png"),
            "site": (_Marked(site) if _inline else site),
            "pc": pc,
            "pc_attr": pc_attr,
            "inline_edit": _inline,
            "canvas_fonts": CANVAS_FONT_CHOICES, "canvas_weights": CANVAS_WEIGHTS,
            # the searchable picker needs the category and the real weight list
            # for each family; the spec map is what lets it fetch one at a time
            "canvas_font_picker": FONT_PICKER,
            "canvas_font_categories": FONT_CATEGORIES,
            "canvas_font_specs": FONT_GOOGLE_SPEC,
            # so the panel can show, and offer to remove, a setting from before
            # every kind of text had its own controls
            "retired_style_fields": RETIRED_STYLE_FIELDS,
            "canvas_cases": CANVAS_CASES, "canvas_shadows": SHADOW_CHOICES,
            "canvas_tssides": TSSIDE_CHOICES, "canvas_italics": ITALIC_CHOICES,
            "canvas_bgsizes": BGSIZE_CHOICES, "canvas_bgposes": BGPOS_CHOICES,
            "canvas_graddirs": GRADDIR_CHOICES, "canvas_filters": FILTER_CHOICES,
            "canvas_valigns": VALIGN_CHOICES,
            "canvas_imgfits": IMGFIT_CHOICES, "canvas_colss": COLS_CHOICES,
            "canvas_xtraposes": XTRAPOS_CHOICES, "canvas_xtraaligns": XTRAALIGN_CHOICES,
            "site_defaults": (_Marked(SITE_IMAGE_DEFAULTS) if _inline else SITE_IMAGE_DEFAULTS),
            "features": feats,
            "nav_links": [n for n in [
                {"label": pc("nav_menu"), "href": "/menu", "hot": False},
                {"label": pc("nav_deals"), "href": "/deals", "hot": True, "feature": "deals"},
                {"label": pc("nav_catering"), "href": "/catering", "hot": False},
                {"label": pc("nav_locations"), "href": "/locations", "hot": False},
                {"label": pc("nav_about"), "href": "/about", "hot": False},
                {"label": pc("nav_more"), "href": more_children[0]["href"] if more_children else "/contact",
                 "hot": False, "children": more_children},
            ] if feats.get(n.get("feature"), True) and n.get("children") != []],
            "all_stores": stores,
            "current_store": current,
            "cart_count": sum(i.get("qty", 0) for i in session.get("cart", [])),
            "current_user": user,
            "favorite_ids": favorite_ids,
            "order_type": session.get("order_type", "delivery"),
            "schedule_at": session.get("schedule_at"),
            "needs_location": not session.get("context_set"),
            "csrf_token": get_csrf_token(),
        }

    # ── CLI ─────────────────────────────────────────────────────
    @app.cli.command("db-create")
    def db_create():
        """Create all tables (initial scaffold; use Alembic migrations after)."""
        db.create_all()
        print("[ok] tables created")

    @app.cli.command("seed")
    def seed():
        """Seed roles + two locations, each with its own menu & integrations."""
        from .seed_data import run_seed
        run_seed()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    # ── Error pages ─────────────────────────────────────────────
    # Without these a mistyped URL or a dead link showed Werkzeug's bare
    # "Not Found" page: no header, no way back into the site.
    ERRORS = {
        400: ("That request didn't look right",
              "Something in the form or link was malformed. Try again from the page you came from."),
        403: ("You don't have access to that",
              "That area needs a different account. Sign in with the right one, or head back to the menu."),
        404: ("We couldn't find that page",
              "The link may be old, or the page may have moved. Everything else is still where you left it."),
        413: ("That file was too large",
              "Pick a smaller image and upload it again."),
        429: ("Slow down a moment",
              "Too many requests in a short time. Wait a few seconds and try again."),
        500: ("Something went wrong on our side",
              "The team has been notified. Please try again in a moment."),
    }

    def _render_error(code):
        heading, message = ERRORS[code]
        # An API/JSON caller should not be handed an HTML page.
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return {"error": heading, "code": code}, code
        try:
            return render_template("errors/error.html", code=code,
                                   heading=heading, message=message), code
        except Exception:            # a broken template must not mask the real error
            return heading, code

    for _code in ERRORS:
        app.register_error_handler(_code, lambda e, c=_code: _render_error(c))

    return app
