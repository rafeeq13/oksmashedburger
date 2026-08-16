"""Public storefront pages that aren't menu/stores specific."""
import re
import secrets

from flask import Blueprint, render_template, request, redirect, flash, current_app, g
from markupsafe import escape

from app.extensions import db, limiter
from app.helpers import get_current_store
from app.models.promo import Coupon, GiftCard
from app.models.contact import ContactMessage, Subscriber
from app.models.review import Review
from app.models.page import home_sections_ordered, BuilderPage, DYNAMIC_SECTION_KEYS
from app.auth import current_user

bp = Blueprint("website", __name__)

_PB_EDIT_ROLES = {"super_admin", "franchise_owner", "store_manager"}

# A builder page can drop live "dynamic section" blocks; on render we replace each
# <section data-dyn="KEY">…</section> placeholder with the real, data-driven partial.
# The key pattern allows digits so the Page Builder's own `custom_1`, `custom_2`
# blocks are dynamic sections too, not unknown keys left as empty placeholders.
_DYN_RE = re.compile(r'''<section\b[^>]*\bdata-dyn=["']([a-zA-Z0-9_]+)["'][^>]*>.*?</section>''',
                     re.DOTALL | re.IGNORECASE)
_DYN_SET = set(DYNAMIC_SECTION_KEYS)

# Everything a "pure section page" may contain besides its placeholders: HTML
# comments and whitespace. Such a page carries no free-form builder content, so
# the section system (order, show/hide, custom blocks) can own it outright.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _menu_context():
    store = get_current_store()
    menu = store.effective_menu() if store else []
    best = [it for grp in menu for it in grp["items"] if it["featured"] and it["available"]][:4]
    if len(best) < 4:
        best = [it for grp in menu for it in grp["items"] if it["available"]][:4]
    categories = [grp["category"] for grp in menu]
    return categories, best



# Fields that are text a person reads. Everything else in a section's config is
# a link, a theme name or an image URL, and wrapping those in a <span> would
# land markup inside an attribute.
# Fields that are NOT words on the page. A value here is wrapped in an editable
# <span>, so anything a template puts inside an attribute has to be left alone:
# href="…/<span …>oksmashedburger</span>/reels/" closes the tag early and the
# rest of it lands on the page as text, which is exactly what the Instagram
# reels grid did. tests/test_smoke.py re-derives this list from the templates,
# so a new field used in an attribute fails there instead of on the page.
_NON_TEXT = ("_href", "theme", "image", "img", "handle")


def _editable_cfg(key, cfg):
    """In edit mode, hand the template values that are already editable spans.

    Home sections read their words out of `cfg`, not out of pc(), which is why
    they were the one page you could restyle but not rewrite on the page. The
    registry defaults are merged in first, so a field nobody has overridden yet
    is editable too — otherwise only already-changed text could be changed.
    """
    from flask import request
    from app.auth import current_user
    from app.models.page import spec_for, resolved_defaults
    from markupsafe import Markup, escape

    u = current_user()
    editing = (bool(request.args.get("edit")) and u is not None
               and u.role is not None
               and u.role.name in ("super_admin", "franchise_owner", "store_manager"))
    if not editing:
        return cfg

    try:
        defaults = resolved_defaults(current_app.config.get("BRAND_NAME", "")).get(key, {})
    except Exception:
        defaults = {}
    spec_fields = {f[0] for f in (spec_for(key) or {}).get("fields", [])}

    merged = dict(defaults)
    merged.update({k: v for k, v in (cfg or {}).items() if v not in (None, "")})

    out = {}
    for k, v in merged.items():
        if (k in spec_fields and isinstance(v, str) and v
                and not any(k.endswith(t) or k == t for t in _NON_TEXT)
                and not k.startswith("style_")):
            out[k] = Markup('<span class="ok-ie ok-ie-sc" data-sc="%s" data-scsec="%s"'
                            ' title="Click to edit">%s</span>'
                            % (escape(k), escape(key), escape(v)))
        else:
            out[k] = v
    return out

def _render_section(row, key, categories, best, style_of):
    """One home section, wrapped in the same `.pb-sec` shell index.html uses."""
    cfg = (row.config if row else None) or {}
    cfg = _editable_cfg(key, cfg)
    tpl = ("website/sections/custom.html" if key.startswith("custom_")
           else "website/sections/%s.html" % key)
    try:
        inner = render_template(tpl, cfg=cfg, sec=row,
                                categories=categories, best_sellers=best)
    except Exception as e:
        # Swallowing this kept the page up but made a broken section disappear
        # silently, which is very hard to diagnose. Keep the page up, but say so.
        current_app.logger.exception("dynamic section %r failed to render: %s", key, e)
        return ""
    style = style_of(cfg) if style_of else ""
    # data-page is what the on-page design panel posts back; without it the
    # panel had no idea which page's section it was styling and every save on
    # the home page came back 400.
    return '<div class="pb-sec" data-page="home" data-section="%s" data-sid="%s" data-label="%s"%s>%s</div>' % (
        escape(key), escape(str(row.id) if row else ""), escape(row.label if row else key),
        (' style="%s"' % escape(style)) if style else "", inner)


def expand_dynamic(html, home=False, include_hidden=False):
    """Replace dynamic-section placeholders in builder HTML with live partials.

    Each expanded block is wrapped in the same `.pb-sec` shell the section-based
    home uses and is rendered with its PageSection config, so text edits and the
    Visual Editor's section/card styling apply here too. Without this the admin
    could save changes in /admin/canvas and see nothing on a builder-served home.

    `home=True` additionally makes the page obey the Page Builder, which is the
    admin screen that describes the home and nothing else:

      * a section switched off there renders as nothing (it used to render
        regardless, so hiding a section had no effect at all on the live home),
      * custom blocks added there are appended, since they are created after the
        builder page and so have no placeholder in its HTML.

    On any other builder page a live block was dropped in deliberately, so it
    renders whatever the home's visibility happens to be.

    `include_hidden` keeps hidden sections in for the admin's own edit preview,
    where they still have to be selectable in order to be switched back on.
    """
    if not html:
        return ""
    categories, best = _menu_context()
    rows = {s.key: s for s in home_sections_ordered()}
    style_of = current_app.jinja_env.globals.get("pb_section_style")
    seen = set()

    def repl(m):
        key = m.group(1).lower()               # tolerate data-dyn="Hero" etc.
        row = rows.get(key)
        if key not in _DYN_SET and row is None:
            return m.group(0)                  # unknown key → leave the block untouched
        seen.add(key)
        if home and row is not None and not row.enabled and not include_hidden:
            return ""                          # switched off in the Page Builder
        return _render_section(row, key, categories, best, style_of)

    out = _DYN_RE.sub(repl, html) if "data-dyn" in html else html

    if home:
        extra = [r for r in rows.values()
                 if r.key.startswith("custom_") and r.key not in seen
                 and (r.enabled or include_hidden)]
        out += "".join(_render_section(r, r.key, categories, best, style_of) for r in extra)
    return out


# GrapesJS hands back its own reset rules from getCss() whether or not the admin
# styled anything. Counting those as "the admin built something here" is what
# would let a single Save in the builder take the home page away from the
# section system for good.
_GJS_BOILERPLATE = re.compile(
    r"\*\s*\{\s*box-sizing\s*:\s*border-box\s*;?\s*\}|body\s*\{\s*margin\s*:\s*0\s*;?\s*\}",
    re.I)


def _real_css(css):
    """The page's own CSS, with the builder's boilerplate discounted."""
    return _GJS_BOILERPLATE.sub("", css or "").strip()


def _is_pure_section_page(page):
    """True when a builder page is nothing but dynamic-section placeholders.

    "Edit home page" seeds the builder with one placeholder per home section and
    no content of its own. Until the admin actually drops a block in, the section
    system is the only thing describing that page, so it should own it completely
    — including the order and the sections added or removed since. Rendering the
    stored placeholder list instead is what made reordering and new custom blocks
    in the Page Builder look like they did nothing.
    """
    if _real_css(page.css) or (page.head_code or "").strip():
        return False
    rest = _DYN_RE.sub("", page.html or "")
    rest = _HTML_COMMENT_RE.sub("", rest)
    return not rest.strip()


def _render_builder_page(page, expanded):
    """Render a page built in the drag-drop editor.

    The one place that names the page's design key, so the <head> can ask
    Google for the family this page chose. Without it the picker's own preview
    made a custom page look right while every visitor got the fallback face,
    and nothing on either admin screen showed the difference.
    """
    g.pb_builder_key = "p:" + page.slug
    return render_template("website/builder_page.html", page=page,
                           expanded_html=expanded)


@bp.before_app_request
def _serve_builder_override():
    """If a published builder page has claimed the current storefront path,
    serve it instead of the default template (lets any page be rebuilt visually)."""
    if request.method != "GET":
        return None
    p = request.path
    if p.startswith(("/admin", "/static", "/api", "/p/", "/driver")):
        return None
    page = BuilderPage.query.filter_by(override_path=p, published=True).first()
    if page:
        return _render_builder_page(page, expand_dynamic(page.html))
    return None


@bp.get("/")
def home():
    u = current_user()
    edit_mode = bool(request.args.get("pbedit")) and u and u.role and u.role.name in _PB_EDIT_ROLES

    # If the admin built a home page in the drag-drop builder, serve that — unless
    # it is still only the seeded section placeholders, in which case the section
    # system describes the page better than the frozen placeholder list does.
    home_page = BuilderPage.query.filter_by(is_home=True, published=True).first()
    if home_page and not _is_pure_section_page(home_page):
        return _render_builder_page(home_page, expand_dynamic(
            home_page.html, home=True, include_hidden=edit_mode))
    # The built-in, section-based home.
    categories, best = _menu_context()
    all_secs = home_sections_ordered()
    home_sections = all_secs if edit_mode else [s for s in all_secs if s.enabled]
    return render_template("website/index.html", best_sellers=best, categories=categories,
                           home_sections=home_sections, pb_edit=edit_mode)


@bp.get("/p/<slug>")
def custom_page(slug):
    page = BuilderPage.query.filter_by(slug=slug, published=True).first_or_404()
    return _render_builder_page(page, expand_dynamic(page.html))


@bp.post("/form-submit")
@limiter.limit("6 per minute; 30 per hour")
def builder_form_submit():
    """Generic handler that GrapesJS-built forms can post to. Stores the fields
    as a contact message and returns the visitor to where they came from."""
    fields = {k: v for k, v in request.form.items() if k not in ("_csrf",)}
    msg = ContactMessage(
        name=fields.get("name") or fields.get("Name") or "Website visitor",
        email=fields.get("email") or fields.get("Email") or "",
        subject=(fields.get("subject") or "Form submission")[:80],
        message="\n".join("%s: %s" % (k, v) for k, v in fields.items()) or "(no fields)")
    db.session.add(msg)
    db.session.commit()
    flash("Thanks! Your message has been received.", "success")
    return redirect(request.referrer or "/")


@bp.get("/about")
def about():
    return render_template("website/about.html")


@bp.get("/contact")
def contact():
    return render_template("website/contact.html")


# Extra fields some forms collect (catering quotes). ContactMessage has no
# columns for them, so they are folded into the message body instead of being
# silently dropped. Order here is the order they appear in the saved message.
_EXTRA_FIELDS = [
    ("phone", "Phone"),
    # catering quotes
    ("event_date", "Event date"),
    ("headcount", "Headcount"),
    ("event_type", "Event type"),
    ("package", "Package"),
    ("location", "Delivery address"),
    ("dietary", "Dietary needs"),
    # job applications
    ("role", "Role"),
    ("preferred_store", "Preferred location"),
    ("availability", "Availability"),
    ("start_date", "Earliest start"),
    ("experience", "Experience"),
    ("portfolio", "CV / profile link"),
    ("eligible", "Eligible to work"),
]


@bp.post("/contact")
@limiter.limit("6 per minute; 30 per hour")
def contact_send():
    msg = request.form.get("message", "").strip()
    back = request.form.get("next", "").strip() or "/contact"
    if not back.startswith("/"):
        back = "/contact"
    if not msg:
        flash("Please enter a message.", "error")
        return redirect(back)

    details = [f"{label}: {v}" for key, label in _EXTRA_FIELDS
               if (v := request.form.get(key, "").strip())]
    if details:
        msg = chr(10).join(details) + chr(10) * 2 + msg

    row = ContactMessage(
        name=request.form.get("name", "").strip(),
        email=request.form.get("email", "").strip(),
        subject=request.form.get("subject", "General enquiry").strip(),
        order_number=request.form.get("order", "").strip(),
        message=msg)
    db.session.add(row)
    db.session.commit()

    # Notify the business and acknowledge the sender. A mail failure must never
    # cost us the submission — the row is already committed above.
    try:
        from app.services import mailer
        mailer.contact_received(row)
    except Exception as e:
        current_app.logger.warning("contact mail failed: %s", e)

    flash("Thanks! Your message has been sent. We'll reply within one business day.", "success")
    return redirect(back)


@bp.get("/catering")
def catering():
    return render_template("website/catering.html")


@bp.get("/careers")
def careers():
    return render_template("website/careers.html")


@bp.get("/news")
def news():
    return render_template("website/news.html")


@bp.get("/faq")
def faq():
    return render_template("website/faq.html")


@bp.get("/deals")
def deals():
    coupons = Coupon.query.filter_by(active=True).order_by(Coupon.created_at.desc()).all()
    return render_template("website/deals.html", coupons=coupons)


@bp.get("/rewards")
def rewards():
    return render_template("website/rewards.html")


@bp.get("/gift-cards")
def gift_cards():
    return render_template("website/gift-cards.html")


@bp.post("/gift-cards/balance")
@limiter.limit("15 per minute")
def gift_card_balance():
    code = request.form.get("code", "").strip().upper()
    gc = GiftCard.query.filter_by(code=code).first()
    if gc:
        flash(f"Gift card {gc.code}: ${gc.balance:.2f} available.", "success")
    else:
        flash("Gift card not found.", "error")
    return redirect("/gift-cards")


@bp.post("/gift-cards/buy")
def gift_card_buy():
    amount = request.form.get("amount", type=float) or 25.0
    amount = max(5.0, min(500.0, amount))
    code = "OKGC-" + secrets.token_hex(3).upper()
    db.session.add(GiftCard(code=code, initial_balance=amount, balance=amount, active=True,
                            recipient_email=request.form.get("recipient", "").strip(),
                            sender_name=request.form.get("sender", "").strip(),
                            message=request.form.get("message", "").strip()))
    db.session.commit()
    try:
        from app.services import mailer
        gc = GiftCard.query.filter_by(code=code).first()
        if mailer.gift_card_issued(gc):
            flash(f"Gift card {code} is on its way to {gc.recipient_email}.", "success")
            return redirect("/gift-cards")
    except Exception as e:
        current_app.logger.warning("gift card mail failed: %s", e)
    flash(f"Gift card created: {code}, ${amount:.2f}. (Demo: no charge. Try it at checkout!)", "success")
    return redirect("/gift-cards")


@bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    """One-click opt-out from the link in every newsletter email.

    Accepts POST as well as GET because RFC 8058 one-click (the button Gmail
    and Outlook render from the List-Unsubscribe header) posts to this URL.
    The token is signed and never expires — an old newsletter should still be
    able to unsubscribe someone years later.
    """
    from itsdangerous import BadSignature, URLSafeSerializer
    try:
        email = URLSafeSerializer(current_app.config["SECRET_KEY"],
                                  salt="ok-unsubscribe").loads(token)
    except BadSignature:
        return render_template("website/unsubscribe.html", email=None, ok=False), 400

    row = Subscriber.query.filter_by(email=email).first()
    if row and row.is_active:
        row.is_active = False
        db.session.commit()
    return render_template("website/unsubscribe.html", email=email, ok=True)


@bp.post("/reviews")
@limiter.limit("3 per minute; 10 per hour")
def review_submit():
    """Public review submission. Every row lands as `pending` — nothing a
    visitor writes reaches the site until a manager approves it."""
    name = request.form.get("name", "").strip()
    body = request.form.get("body", "").strip()
    rating = request.form.get("rating", type=int) or 0
    back = (request.referrer or "/") + "#reviews"

    if not name or not body:
        flash("Please add your name and a few words about your visit.", "error")
        return redirect(back)
    if len(body) < 15:
        flash("Could you tell us a little more? A sentence or two helps.", "error")
        return redirect(back)
    if not 1 <= rating <= 5:
        flash("Please choose a star rating.", "error")
        return redirect(back)

    user = current_user()
    store = get_current_store()
    db.session.add(Review(
        name=name[:80],
        email=(request.form.get("email", "").strip() or (user.email if user else ""))[:255],
        user_id=user.id if user else None,
        rating=rating,
        body=body[:2000],
        store_id=store.id if store else None,
        order_number=request.form.get("order_number", "").strip()[:30],
        status="pending"))
    db.session.commit()
    flash("Thanks! Your review has been sent to us and will appear once it's checked.", "success")
    return redirect(back)


@bp.post("/subscribe")
@limiter.limit("6 per minute; 30 per hour")
def subscribe():
    """Footer newsletter sign-up. Re-subscribing an existing address just
    reactivates it rather than erroring, and we never confirm or deny whether
    an address was already on the list."""
    email = request.form.get("email", "").strip().lower()
    back = request.referrer or "/"
    if "@" not in email or "." not in email.split("@")[-1]:
        flash("Please enter a valid email address.", "error")
        return redirect(back)

    existing = Subscriber.query.filter_by(email=email).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.session.commit()
    else:
        db.session.add(Subscriber(email=email, source="footer"))
        db.session.commit()
        try:
            from app.services import mailer
            mailer.subscribed(email)
        except Exception as e:
            current_app.logger.warning("subscribe mail failed: %s", e)

    flash("You're on the list. Check your inbox!", "success")
    return redirect(back)
