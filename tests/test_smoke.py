"""End-to-end smoke tests.

Everything in here was verified by hand at least once; this file is what keeps
it verified. Runs against the configured database and cleans up after itself —
each test that writes uses an address nobody else would ever use.

    python -m pytest tests -q
"""
import re

import pytest
from dotenv import load_dotenv

# Same first move wsgi.py makes — without it the app falls back to the Postgres
# URL baked into config defaults instead of whatever .env points at.
load_dotenv()

from app import create_app                    # noqa: E402
from app.extensions import db                 # noqa: E402
from app.models.site import SiteSetting      # noqa: E402


@pytest.fixture(scope="session")
def app():
    """No app context is pushed here on purpose.

    Flask's test client reuses an already-active app context instead of
    pushing a fresh one, and `current_user()` memoises onto `g`. Holding one
    context open for the whole session therefore leaks the *first* request's
    user into every later request — anonymous page hits would make the admin
    look logged out. Real requests never share a context, so this is a
    harness concern only. Tests that need the DB open their own context.
    """
    application = create_app()
    application.config["TESTING"] = True

    # The suite runs against the development database, so it inherits whatever
    # state was left there. Feature switches are the sharp edge: one stray
    # "off" row and /news or /gift-cards answer 404, failing tests that have
    # nothing to do with the switch. The suite's premise is a site with
    # everything on, so that is asserted here rather than assumed.
    with application.app_context():
        stray = SiteSetting.query.filter(SiteSetting.key.like("feature_%")).all()
        if stray:
            for row in stray:
                db.session.delete(row)
            db.session.commit()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path="/"):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else ""


def admin_client(app):
    from app.models.user import User
    c = app.test_client()
    with app.app_context():
        uid = User.query.filter(User.role.has(name="super_admin")).first().id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
    return c


# ── every page answers ──────────────────────────────────────────────────────

PUBLIC = ["/", "/menu", "/menu?q=shake", "/about", "/catering", "/careers",
          "/news", "/faq", "/rewards", "/gift-cards", "/deals", "/locations",
          "/contact", "/login", "/register", "/forgot-password", "/cart"]

ADMIN = ["/admin", "/admin/orders", "/admin/customers", "/admin/menu",
         "/admin/coupons", "/admin/gift-cards", "/admin/drivers", "/admin/staff",
         "/admin/locations", "/admin/settings", "/admin/canvas", "/admin/builder",
         "/admin/page-content", "/admin/content", "/admin/site-images",
         "/admin/design", "/admin/theme", "/admin/features", "/admin/reviews",
         "/admin/hours", "/admin/integrations",
         "/admin/notifications", "/admin/messages", "/admin/subscribers"]

# Retired screens keep working as redirects rather than 404s, so an old
# bookmark still lands on the tool that replaced them.
ADMIN_REDIRECTS = [("/admin/page-builder", "/admin/canvas")]


@pytest.mark.parametrize("path", PUBLIC)
def test_public_page_renders(client, path):
    assert client.get(path, follow_redirects=True).status_code == 200


@pytest.mark.parametrize("path", ADMIN)
def test_admin_page_renders(app, path):
    assert admin_client(app).get(path).status_code == 200


@pytest.mark.parametrize("path,target", ADMIN_REDIRECTS)
def test_retired_admin_screen_redirects(app, path, target):
    r = admin_client(app).get(path)
    assert r.status_code in (301, 302), path
    assert target in r.headers["Location"], path


def test_admin_requires_login(client):
    # anonymous visitors are bounced, never served the panel
    assert client.get("/admin").status_code in (302, 401, 403)


# ── content lists drive the site ────────────────────────────────────────────

def test_content_defaults_render_without_any_rows(client):
    html = client.get("/careers").get_data(as_text=True)
    assert "Grill Cook" in html


def test_editing_a_content_item_changes_the_public_page(app):
    with app.app_context():
        from app.models.content import ContentItem, import_defaults
        c = admin_client(app)
        ContentItem.query.filter_by(kind="jobs").delete()
        db.session.commit()
        try:
            import_defaults("jobs")
            row = (ContentItem.query.filter_by(kind="jobs")
                   .order_by(ContentItem.sort_order).first())
            c.post("/admin/content/%d/edit" % row.id, data={
                "_csrf": csrf(c, "/admin/content?kind=jobs"),
                "title": "Test Role ZZZ", "type": "Weekends",
                "where": "Nowhere", "desc": "Only exists during this test."})
            assert "Test Role ZZZ" in c.get("/careers").get_data(as_text=True)

            # hiding it takes it off the site
            c.post("/admin/content/%d/toggle" % row.id,
                   data={"_csrf": csrf(c, "/admin/content?kind=jobs")})
            assert "Test Role ZZZ" not in c.get("/careers").get_data(as_text=True)
        finally:
            ContentItem.query.filter_by(kind="jobs").delete()
            db.session.commit()


def test_number_fields_are_stored_as_numbers(app):
    """Regression: stars arrived as "5" and the star loop raised TypeError,
    which expand_dynamic swallowed — the whole section vanished."""
    with app.app_context():
        from app.models.content import ContentItem, import_defaults
        c = admin_client(app)
        ContentItem.query.filter_by(kind="testimonials").delete()
        db.session.commit()
        try:
            import_defaults("testimonials")
            row = (ContentItem.query.filter_by(kind="testimonials")
                   .order_by(ContentItem.sort_order).first())
            c.post("/admin/content/%d/edit" % row.id, data={
                "_csrf": csrf(c, "/admin/content?kind=testimonials"),
                "name": "Tester", "when": "today", "stars": "5", "text": "Fine."})
            db.session.expire_all()
            assert db.session.get(ContentItem, row.id).data["stars"] == 5
            assert "What locals have to say" in c.get("/").get_data(as_text=True)
        finally:
            ContentItem.query.filter_by(kind="testimonials").delete()
            db.session.commit()


def test_home_serves_every_section_live(client):
    """The builder home used to carry frozen copies of seven sections."""
    html = client.get("/", follow_redirects=True).get_data(as_text=True)
    for key in ["hero", "explore_menu", "best_sellers", "how_it_works", "catering",
                "about", "reviews", "locations", "franchise", "testimonials",
                "instagram"]:
        assert 'data-section="%s"' % key in html, key


# ── forms and email ─────────────────────────────────────────────────────────

def test_contact_form_saves_and_folds_in_extra_fields(app):
    with app.app_context():
        from app.models.contact import ContactMessage
        c = app.test_client()
        c.post("/contact", data={
            "_csrf": csrf(c, "/careers"), "subject": "Job application",
            "name": "PyTest User", "email": "pytest-contact@example.invalid",
            "phone": "2155550000", "role": "Grill Cook", "availability": "Weekends",
            "message": "Body text."})
        row = ContactMessage.query.filter_by(email="pytest-contact@example.invalid").first()
        try:
            assert row is not None
            assert "Role: Grill Cook" in row.message
            assert "Availability: Weekends" in row.message
            assert row.message.endswith("Body text.")
        finally:
            if row:
                db.session.delete(row)
                db.session.commit()


def test_every_site_email_is_attempted_and_logged(app):
    with app.app_context():
        from app.models.notification import Notification
        from app.models.contact import Subscriber
        c = app.test_client()
        before = Notification.query.filter_by(order_id=None).count()
        c.post("/subscribe", data={"_csrf": csrf(c, "/"),
                                   "email": "pytest-sub@example.invalid"})
        try:
            rows = (Notification.query.filter_by(order_id=None)
                    .order_by(Notification.id).offset(before).all())
            assert any(n.event == "subscribed" for n in rows)
        finally:
            Subscriber.query.filter_by(email="pytest-sub@example.invalid").delete()
            Notification.query.filter_by(recipient="pytest-sub@example.invalid").delete()
            db.session.commit()


def test_unsubscribe_is_one_click_and_signed(app):
    with app.app_context():
        from app.models.contact import Subscriber
        from app.models.notification import Notification
        from app.services import mailer
        c = app.test_client()
        c.post("/subscribe", data={"_csrf": csrf(c, "/"),
                                   "email": "pytest-opt@example.invalid"})
        try:
            with app.test_request_context("/"):
                link = mailer.unsubscribe_link("pytest-opt@example.invalid")
            path = "/" + link.split("/", 3)[3]
            # RFC 8058 one-click posts with no session and no CSRF token
            assert c.post(path).status_code == 200
            assert Subscriber.query.filter_by(
                email="pytest-opt@example.invalid").first().is_active is False
            assert c.get("/unsubscribe/tampered").status_code == 400
        finally:
            Subscriber.query.filter_by(email="pytest-opt@example.invalid").delete()
            Notification.query.filter_by(recipient="pytest-opt@example.invalid").delete()
            db.session.commit()


def test_password_reset_link_is_single_use(app):
    with app.app_context():
        from app.models.user import User, Role
        from app.blueprints.auth import _reset_token
        c = app.test_client()
        user = User(email="pytest-reset@example.invalid", first_name="Py",
                    role=Role.query.filter_by(name="customer").first())
        user.set_password("originalpass")
        db.session.add(user)
        db.session.commit()
        try:
            token = _reset_token(user)
            assert c.get("/reset-password/" + token).status_code == 200
            c.post("/reset-password/" + token, data={
                "_csrf": csrf(c, "/reset-password/" + token),
                "password": "brandnewpass", "confirm": "brandnewpass"})
            db.session.expire_all()
            user = User.query.filter_by(email="pytest-reset@example.invalid").first()
            assert user.check_password("brandnewpass")
            assert not user.check_password("originalpass")
            # the same link must not work twice
            body = c.get("/reset-password/" + token,
                         follow_redirects=True).get_data(as_text=True)
            assert "already been used" in body
        finally:
            User.query.filter_by(email="pytest-reset@example.invalid").delete()
            db.session.commit()


# ── hardening ───────────────────────────────────────────────────────────────

def test_csrf_is_enforced_on_posts(client):
    assert client.post("/contact", data={"message": "no token"}).status_code == 400


def test_password_reset_is_rate_limited(app):
    c = app.test_client()
    token = csrf(c, "/forgot-password")
    codes = [c.post("/forgot-password",
                    data={"_csrf": token, "email": "pytest-rl@example.invalid"}).status_code
             for _ in range(7)]
    assert 429 in codes, "forgot-password accepted 7 rapid requests"


def test_security_headers_present(client):
    h = client.get("/").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "SAMEORIGIN"
    assert "Referrer-Policy" in h


def test_static_assets_are_versioned(client):
    html = client.get("/").get_data(as_text=True)
    assert re.search(r'/static/css/premium\.css\?v=\d+', html)


def test_no_storefront_field_is_missing_an_accessible_name():
    """Regression guard for the 16 inputs that had no label, aria-label or
    placeholder — a screen reader announced them as nothing at all."""
    import glob
    import os

    def wrapped_in_label(src, pos):
        i = src.rfind("<label", 0, pos)
        if i == -1:
            return False
        j = src.find("</label>", i)
        return j != -1 and j > pos

    unnamed = []
    for path in glob.glob("app/templates/**/*.html", recursive=True):
        rel = path.replace(os.sep, "/")
        if "/admin/" in rel:
            continue
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(r"<(input|select|textarea)\b[^>]*>", src):
            tag = m.group(0)
            if 'type="hidden"' in tag or "aria-label" in tag or "placeholder" in tag:
                continue
            fid = re.search(r'id="([^"]+)"', tag)
            if fid and ('for="%s"' % fid.group(1)) in src:
                continue
            if wrapped_in_label(src, m.start()):
                continue
            unnamed.append("%s: %s" % (rel, tag[:70]))
    assert not unnamed, "fields with no accessible name:\n" + "\n".join(unnamed)


# ── theme, page design and inline editing ───────────────────────────────

def test_theme_is_off_until_the_client_changes_something(client):
    assert 'id="ok-theme"' not in client.get("/", follow_redirects=True).get_data(as_text=True)


def test_theme_repaints_every_page(app):
    from app.models.site import SiteSetting
    c = admin_client(app)
    with app.app_context():
        try:
            c.post("/admin/theme", data={"_csrf": csrf(c, "/admin/theme"),
                                         "theme_primary": "#FF3B30",
                                         "theme_radius_control": "2"})
            for path in ("/", "/menu", "/about", "/rewards"):
                html = c.get(path, follow_redirects=True).get_data(as_text=True)
                assert "--ok-yellow:#FF3B30" in html, path
                assert "--r-control:2px" in html, path
        finally:
            c.post("/admin/theme/reset", data={"_csrf": csrf(c, "/admin/theme")})
            assert SiteSetting.query.filter(SiteSetting.key.like("theme_%")).count() == 0


def test_every_inner_page_section_is_styleable(app):
    """Regression: styling only ever reached the home page."""
    from app.models.page import INNER_PAGES, PageSection
    c = admin_client(app)
    with app.app_context():
        assert len(INNER_PAGES) == 9
        for spec in INNER_PAGES:
            html = c.get(spec["url"], follow_redirects=True).get_data(as_text=True)
            assert html.count('class="pb-sec"') == len(spec["sections"]), spec["page"]

        try:
            c.post("/admin/design/careers/why_work_here", data={
                "_csrf": csrf(c, "/admin/design?page=careers"),
                "style_bg": "#101820", "style_cardradius": "20"})
            html = c.get("/careers").get_data(as_text=True)
            assert "--pb-bg:#101820" in html
            assert "--pb-cardradius:20px" in html
        finally:
            PageSection.query.filter_by(page="careers").delete()
            db.session.commit()


def test_inline_editing_is_admin_only_and_saves(app):
    """No app context is held around the requests here on purpose: this test
    mixes an anonymous client and an admin one, and current_user() memoises
    onto `g`, which a shared context would leak between them (see the `app`
    fixture). DB work opens its own short context."""
    import json
    from app.models.site import SiteSetting

    anon = app.test_client()
    c = admin_client(app)

    # a visitor can never see it, even with ?edit=1
    assert "okIeBar" not in anon.get("/about?edit=1").get_data(as_text=True)
    assert 'class="ok-ie"' not in anon.get("/about").get_data(as_text=True)

    page = c.get("/about?edit=1").get_data(as_text=True)
    assert "okIeBar" in page
    # every pc() field on the page — About's own plus the site-wide footer —
    # becomes editable. Derived, not a literal, so adding copy to the registry
    # does not "fail" this test for doing exactly what it is meant to do.
    from app.models.page import PAGE_CONTENT
    by_key = {p["key"]: p for p in PAGE_CONTENT}
    expected = len(by_key["about"]["fields"]) + sum(
        1 for f in by_key["footer"]["fields"] if not f[0].endswith("_url"))
    assert page.count('class="ok-ie"') == expected
    # and the public HTML stays clean when the flag is absent
    assert 'class="ok-ie"' not in c.get("/about").get_data(as_text=True)

    hdr = {"Content-Type": "application/json", "X-CSRF-Token": csrf(c, "/about")}
    try:
        r = c.post("/admin/inline-save", headers=hdr,
                   data=json.dumps({"key": "about_hero_heading", "value": "Edited Inline"}))
        assert r.status_code == 200
        assert "Edited Inline" in anon.get("/about").get_data(as_text=True)

        # the endpoint must not become a way to write arbitrary settings rows
        bad = c.post("/admin/inline-save", headers=hdr,
                     data=json.dumps({"key": "not_a_field", "value": "x"}))
        assert bad.status_code == 400

        # an anonymous post is turned away and writes nothing
        anon.post("/admin/inline-save",
                  headers={"Content-Type": "application/json",
                           "X-CSRF-Token": csrf(anon, "/about")},
                  data=json.dumps({"key": "about_hero_heading", "value": "HACKED"}))
        assert "HACKED" not in anon.get("/about").get_data(as_text=True)
    finally:
        with app.app_context():
            SiteSetting.query.filter_by(key="about_hero_heading").delete()
            db.session.commit()


def test_a_switched_off_feature_stops_pricing_not_just_showing(app):
    """Turning Deals off has to remove the money, not only the promo box.

    Hiding the form while an already-applied code kept discounting was the
    actual bug: the order summary still showed a Discount line and the total
    was still reduced on a site where Deals was switched off.

    The switch is left off inside the `try` on purpose — the fixture builds the
    real app against the real database, so the `finally` matters: a stray "off"
    row would follow every later test into a site with no Deals page.
    """
    from app.extensions import db
    from app.models.site import SiteSetting
    from app.models.promo import Coupon
    from app.models.menu import Product
    from app.helpers import get_current_store
    import app.cart as cartlib

    with app.app_context():
        coupon = Coupon.query.filter_by(active=True).first()
        product = Product.query.filter_by(is_active=True).first()
        assert coupon and product, "seed data needs a live coupon and product"
        code, pid, slug = coupon.code, product.id, product.slug

    def totals():
        with app.test_request_context("/cart"):
            from flask import session
            session["cart"] = [{"product_id": pid, "slug": slug, "name": "x", "image": "",
                                "unit_price": 11.49, "qty": 2, "options": {}}]
            session["promo"] = code
            return cartlib.summary(get_current_store())

    def set_deals(off):
        with app.app_context():
            row = SiteSetting.query.filter_by(key="feature_deals").first()
            if off and not row:
                db.session.add(SiteSetting(key="feature_deals", value="off"))
            elif off:
                row.value = "off"
            elif row:
                db.session.delete(row)
            db.session.commit()

    try:
        on = totals()
        assert on["promo"]["code"] == code

        set_deals(True)
        off = totals()
        assert off["promo"]["code"] is None, "a switched-off deal must not resolve"
        assert off["order_discount"] == 0
        assert off["promo"]["discount"] == 0 and off["promo"]["delivery_discount"] == 0
        assert off["total"] >= on["total"], "the total must not stay discounted"

        # and the write side refuses too, so a direct POST cannot re-apply it
        c = app.test_client()
        assert c.post("/cart/promo", data={"_csrf": csrf(c, "/cart"), "promo": code}
                      ).status_code == 404
    finally:
        set_deals(False)

    assert totals()["promo"]["code"] == code, "switching back must restore the deal"


def test_saving_one_pages_words_leaves_the_other_pages_alone(app):
    """The per-page editor posts only its own fields.

    page_content_save() used to walk the whole registry and delete any field it
    could not find in the request, which is fine for the one big form it was
    written for and destructive for a form that covers a single page: saving
    Contact would have wiped About, Careers and the footer.
    """
    from app.extensions import db
    from app.models.site import SiteSetting

    c = admin_client(app)
    try:
        c.post("/admin/page-content", data={
            "_csrf": csrf(c, "/admin/page-content"),
            "about_hero_heading": "ABOUT MARKER",
            "footer_tagline": "FOOTER MARKER"})
        assert "ABOUT MARKER" in c.get("/about").get_data(as_text=True)

        # the per-page panel on the design screen carries Contact's fields only
        c.post("/admin/page-content", data={
            "_csrf": csrf(c, "/admin/design?page=contact"),
            "next": "/admin/design?page=contact",
            "contact_form_heading": "CONTACT MARKER"})

        page = c.get("/contact").get_data(as_text=True)
        assert "CONTACT MARKER" in page
        assert "FOOTER MARKER" in page, "the footer must not be wiped"
        assert "ABOUT MARKER" in c.get("/about").get_data(as_text=True), \
            "another page's copy must not be wiped"
    finally:
        with app.app_context():
            SiteSetting.query.filter(SiteSetting.key.in_(
                ["about_hero_heading", "footer_tagline", "contact_form_heading"])).delete(
                synchronize_session=False)
            db.session.commit()


def test_every_storefront_image_has_an_admin_source():
    """No picture on the storefront may be reachable only by editing code.

    Scans the templates rather than a hand-kept list, so a new hard-coded
    <img> added later fails here instead of quietly becoming another thing the
    client has to ask a developer to change.
    """
    import os
    import re

    skip_dirs = {"admin", "layouts", "errors"}
    guard = re.compile(r"\{%-?\s*if\s+[^%]*?(?:site\.get|image_url|\.img\b|cfg\.get)[^%]*?-?%\}")
    offenders = []

    for dirpath, dirs, files in os.walk("app/templates"):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            html = open(path, encoding="utf-8").read()
            # <img src> and <video poster> both put a picture on the page. The
            # first sweep looked at <img> only, which is how the About video's
            # poster stayed wired to another slot without anyone noticing.
            for m in re.finditer(r"<(?:img|video)\b[^>]*>", html, re.S):
                tag = m.group(0)
                src = (re.search(r'(?:src|poster)="([^"]*)"', tag) or [None, ""])[1]
                if tag.startswith("<video") and not src:
                    continue
                editable = any(t in src for t in (
                    "site.get", "site_defaults", "image_url", "logo_url",
                    "avatar", ".img", "cfg.get", "lead.", "line.image", "img }}"))
                if editable:
                    continue
                if "data-ph" in tag:
                    # fine as the fallback arm of an admin-set source
                    before = html[max(0, m.start() - 320):m.start()]
                    if "{% else %}" in before and guard.search(before[:before.rindex("{% else %}")]):
                        continue
                offenders.append("%s: %s" % (path.replace("\\", "/"), src[:60] or tag[:60]))

    assert not offenders, "images with no admin source:\n  " + "\n  ".join(offenders)
