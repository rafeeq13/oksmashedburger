"""Application factory — OK Smashed Burger platform (modular monolith)."""
import os
from flask import Flask, render_template, request, session

from .config import get_config
from .extensions import db, migrate, jwt, limiter


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
        return resp

    # ── Template context: header/footer need current store, nav, cart, user ──
    from .models.store import Store
    from .auth import current_user
    from .security import get_csrf_token

    def pb_section_style(cfg):
        """Inline CSS (vars + props) for a page-builder section wrapper, built
        from its style_* config. Paired with the .pb-sec rules in style.css."""
        cfg = cfg or {}
        parts = []
        for k, var in (("style_bg", "--pb-bg"), ("style_hcolor", "--pb-hcolor"),
                       ("style_tcolor", "--pb-tcolor"), ("style_font", "--pb-font"),
                       ("style_overlay", "--pb-overlay"),
                       # card-level styling (Visual Editor "Cards" controls)
                       ("style_cardbg", "--pb-cardbg"), ("style_cardborder", "--pb-cardborder"),
                       ("style_cardhead", "--pb-cardhead"), ("style_cardtext", "--pb-cardtext")):
            if cfg.get(k) not in (None, ""):
                parts.append("%s:%s" % (var, cfg[k]))
        if cfg.get("style_cardradius") not in (None, ""):
            parts.append("--pb-cardradius:%spx" % cfg["style_cardradius"])
        if cfg.get("style_pt") not in (None, ""):
            parts.append("padding-top:%spx" % cfg["style_pt"])
        if cfg.get("style_pb") not in (None, ""):
            parts.append("padding-bottom:%spx" % cfg["style_pb"])
        if cfg.get("style_align"):
            parts.append("text-align:%s" % cfg["style_align"])
        return ";".join(parts)

    app.jinja_env.globals["pb_section_style"] = pb_section_style

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
        from .models.site import SiteSetting, SITE_IMAGE_DEFAULTS
        from .models.page import BuilderPage, page_content_defaults
        site = {s.key: s.value for s in SiteSetting.query.all() if s.value}

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
        more_children = [
            {"label": "Rewards", "href": "/rewards"},
            {"label": "Gift Cards", "href": "/gift-cards"},
            {"label": "Contact", "href": "/contact"},
            {"label": "Join Our Team", "href": "/careers"},
            {"label": "News", "href": "/news"},
        ]
        for p in BuilderPage.query.filter_by(show_in_nav=True, published=True).order_by(BuilderPage.title).all():
            more_children.append({"label": p.title, "href": "/p/" + p.slug})
        return {
            "brand_name": app.config["BRAND_NAME"],
            "site": site,
            "pc": pc,
            "pc_attr": pc_attr,
            "inline_edit": _inline,
            "site_defaults": SITE_IMAGE_DEFAULTS,
            "nav_links": [
                {"label": "Menu", "href": "/menu", "hot": False},
                {"label": "Deals", "href": "/deals", "hot": True},
                {"label": "Catering", "href": "/catering", "hot": False},
                {"label": "Locations", "href": "/locations", "hot": False},
                {"label": "About Us", "href": "/about", "hot": False},
                {"label": "More", "href": "/rewards", "hot": False, "children": more_children},
            ],
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
