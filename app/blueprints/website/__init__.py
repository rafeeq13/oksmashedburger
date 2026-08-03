"""Public storefront pages that aren't menu/stores specific."""
import re
import secrets

from flask import Blueprint, render_template, request, redirect, flash, current_app
from markupsafe import escape

from app.extensions import db, limiter
from app.helpers import get_current_store
from app.models.promo import Coupon, GiftCard
from app.models.contact import ContactMessage, Subscriber
from app.models.page import home_sections_ordered, BuilderPage, DYNAMIC_SECTION_KEYS
from app.auth import current_user

bp = Blueprint("website", __name__)

_PB_EDIT_ROLES = {"super_admin", "franchise_owner", "store_manager"}

# A builder page can drop live "dynamic section" blocks; on render we replace each
# <section data-dyn="KEY">…</section> placeholder with the real, data-driven partial.
_DYN_RE = re.compile(r'''<section\b[^>]*\bdata-dyn=["']([a-zA-Z_]+)["'][^>]*>.*?</section>''',
                     re.DOTALL | re.IGNORECASE)
_DYN_SET = set(DYNAMIC_SECTION_KEYS)


def _menu_context():
    store = get_current_store()
    menu = store.effective_menu() if store else []
    best = [it for grp in menu for it in grp["items"] if it["featured"] and it["available"]][:4]
    if len(best) < 4:
        best = [it for grp in menu for it in grp["items"] if it["available"]][:4]
    categories = [grp["category"] for grp in menu]
    return categories, best


def expand_dynamic(html):
    """Replace dynamic-section placeholders in builder HTML with live partials.

    Each expanded block is wrapped in the same `.pb-sec` shell the section-based
    home uses and is rendered with its PageSection config, so text edits and the
    Visual Editor's section/card styling apply here too. Without this the admin
    could save changes in /admin/canvas and see nothing on a builder-served home.
    """
    if not html or "data-dyn" not in html:
        return html or ""
    categories, best = _menu_context()
    rows = {s.key: s for s in home_sections_ordered()}
    style_of = current_app.jinja_env.globals.get("pb_section_style")

    def repl(m):
        key = m.group(1).lower()               # tolerate data-dyn="Hero" etc.
        if key not in _DYN_SET:
            return m.group(0)                  # unknown key → leave the block untouched
        row = rows.get(key)
        cfg = (row.config if row else None) or {}
        try:
            inner = render_template("website/sections/%s.html" % key, cfg=cfg,
                                    categories=categories, best_sellers=best)
        except Exception as e:
            # Swallowing this kept the page up but made a broken section
            # disappear silently, which is very hard to diagnose. Keep the
            # page up, but say so.
            current_app.logger.exception("dynamic section %r failed to render: %s", key, e)
            return ""
        style = style_of(cfg) if style_of else ""
        return '<div class="pb-sec" data-section="%s" data-sid="%s" data-label="%s"%s>%s</div>' % (
            escape(key), escape(str(row.id) if row else ""), escape(row.label if row else key),
            (' style="%s"' % escape(style)) if style else "", inner)

    return _DYN_RE.sub(repl, html)


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
        return render_template("website/builder_page.html", page=page,
                               expanded_html=expand_dynamic(page.html))
    return None


@bp.get("/")
def home():
    # If the admin built a home page in the drag-drop builder, serve that.
    home_page = BuilderPage.query.filter_by(is_home=True, published=True).first()
    if home_page:
        return render_template("website/builder_page.html", page=home_page,
                               expanded_html=expand_dynamic(home_page.html))
    # Otherwise the built-in, section-based home.
    categories, best = _menu_context()
    u = current_user()
    edit_mode = bool(request.args.get("pbedit")) and u and u.role and u.role.name in _PB_EDIT_ROLES
    all_secs = home_sections_ordered()
    home_sections = all_secs if edit_mode else [s for s in all_secs if s.enabled]
    return render_template("website/index.html", best_sellers=best, categories=categories,
                           home_sections=home_sections, pb_edit=edit_mode)


@bp.get("/p/<slug>")
def custom_page(slug):
    page = BuilderPage.query.filter_by(slug=slug, published=True).first_or_404()
    return render_template("website/builder_page.html", page=page,
                           expanded_html=expand_dynamic(page.html))


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
