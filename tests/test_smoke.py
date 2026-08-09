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
         "/admin/page-builder", "/admin/page-content", "/admin/content",
         "/admin/site-images", "/admin/hours", "/admin/integrations",
         "/admin/notifications", "/admin/messages", "/admin/subscribers"]


@pytest.mark.parametrize("path", PUBLIC)
def test_public_page_renders(client, path):
    assert client.get(path, follow_redirects=True).status_code == 200


@pytest.mark.parametrize("path", ADMIN)
def test_admin_page_renders(app, path):
    assert admin_client(app).get(path).status_code == 200


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
