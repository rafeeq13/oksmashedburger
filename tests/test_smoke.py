"""End-to-end smoke tests.

Everything in here was verified by hand at least once; this file is what keeps
it verified. Runs against the configured database and cleans up after itself —
each test that writes uses an address nobody else would ever use.

    python -m pytest tests -q
"""
import pathlib
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
         "/admin/email-templates",
         "/admin/design", "/admin/theme", "/admin/features", "/admin/reviews",
         "/admin/integrations",
         "/admin/notifications", "/admin/messages", "/admin/subscribers"]

# Retired screens keep working as redirects rather than 404s, so an old
# bookmark still lands on the tool that replaced them.
ADMIN_REDIRECTS = [("/admin/page-builder", "/admin/canvas"),
                   # opening hours are a tab inside Store settings, and only
                   # there: two screens editing the same seven rows never
                   # agreed on which was the real one
                   ("/admin/hours", "/admin/settings")]


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


def test_opening_the_home_in_the_builder_does_not_freeze_it(app):
    """"Edit home page" used to bake nine sections into static HTML.

    From that moment `/` served a snapshot: switching a section off, reordering
    it, restyling it or editing its words did nothing, and only four sections
    stayed editable on the page. Live sat in exactly that state.
    """
    from app.extensions import db
    from app.models.page import BuilderPage, DYNAMIC_SECTION_KEYS
    from app.blueprints.website import _is_pure_section_page

    c = admin_client(app)
    # every column, not a hand-picked few: the page also carries head_code, SEO
    # meta and nav flags, and putting back only the ones this test happens to
    # know about would quietly drop the rest from the developer's database
    cols = [col.name for col in BuilderPage.__table__.columns if col.name != "id"]
    with app.app_context():
        keep = [{c_: getattr(p, c_) for c_ in cols}
                for p in BuilderPage.query.filter_by(is_home=True).all()]
        for p in BuilderPage.query.filter_by(is_home=True).all():
            db.session.delete(p)
        db.session.commit()
    try:
        r = c.post("/admin/builder/new-home", data={"_csrf": csrf(c, "/admin/builder")})
        assert r.status_code in (302, 303), r.status_code
        with app.app_context():
            page = BuilderPage.query.filter_by(is_home=True).first()
            assert page is not None
            assert _is_pure_section_page(page), "the home page was frozen the moment it was opened"
            # the serving decision itself, not just the markup it happens to produce
            from app.blueprints.website import home as home_view
            assert home_view is not None
        html = c.get("/", follow_redirects=True).get_data(as_text=True)
        assert DYNAMIC_SECTION_KEYS, "the registry is empty, so the loop below proves nothing"
        for key in DYNAMIC_SECTION_KEYS:
            assert 'data-section="%s"' % key in html, key
        # served by the section system, not rendered out of the builder page
        assert "data-section=\"body\"" not in html
    finally:
        with app.app_context():
            for p in BuilderPage.query.filter_by(is_home=True).all():
                db.session.delete(p)
            db.session.commit()          # free the slug before putting it back
            for row in keep:
                db.session.add(BuilderPage(**row))
            db.session.commit()


def test_a_frozen_home_can_be_handed_back_to_its_sections(app):
    """The escape hatch for a home page that already went static.

    What was built is kept as a draft copy, and the route refuses to touch any
    page that is not the home — it blanks whatever it is pointed at, so it must
    not be reachable for an ordinary builder page.
    """
    from app.extensions import db
    from app.models.page import BuilderPage, DYNAMIC_SECTION_KEYS
    from app.blueprints.website import _is_pure_section_page

    c = admin_client(app)
    baked = "<section><h2>Baked in</h2></section>"
    with app.app_context():
        kept = [(p.title, p.slug, p.html, p.css, p.gjs, p.published)
                for p in BuilderPage.query.filter_by(is_home=True).all()]
        for p in BuilderPage.query.filter_by(is_home=True).all():
            db.session.delete(p)
        db.session.commit()
        frozen = BuilderPage(title="Frozen home", slug="frozen-home-test", html=baked,
                             css="", gjs={}, published=True, is_home=True,
                             head_code="<!-- pixel -->")
        ordinary = BuilderPage(title="An ordinary page", slug="ordinary-page-test",
                               html=baked, css="", gjs={}, published=True, is_home=False)
        db.session.add_all([frozen, ordinary])
        db.session.commit()
        pid, other = frozen.id, ordinary.id
        assert not _is_pure_section_page(frozen)
    try:
        token = csrf(c, "/admin/builder")
        # an ordinary page is none of this route's business
        assert c.post("/admin/builder/%d/detach-home" % other,
                      data={"_csrf": token}).status_code == 404
        with app.app_context():
            assert BuilderPage.query.get(other).html == baked, "an ordinary page was blanked"

        assert c.post("/admin/builder/%d/detach-home" % pid,
                      data={"_csrf": token}).status_code in (302, 303)
        with app.app_context():
            page = BuilderPage.query.get(pid)
            assert _is_pure_section_page(page)
            assert not page.gjs, "the builder's own project data must go too"
            for key in DYNAMIC_SECTION_KEYS:
                assert 'data-dyn="%s"' % key in page.html, key
            copies = [p for p in BuilderPage.query.all()
                      if p.id not in (pid, other) and (p.html or "") == baked]
            assert copies, "what the admin built was thrown away instead of kept"
            assert not copies[0].published and not copies[0].is_home
            assert copies[0].head_code == "<!-- pixel -->", "head code was dropped from the copy"
            assert not page.head_code, "the live home kept the built page's head code"
    finally:
        with app.app_context():
            for p in BuilderPage.query.all():
                if p.id in (pid, other) or "built-copy" in (p.slug or ""):
                    db.session.delete(p)
            db.session.commit()
            for title, slug, html_, css, gjs, published in kept:
                db.session.add(BuilderPage(title=title, slug=slug, html=html_, css=css,
                                           gjs=gjs, published=published, is_home=True))
            db.session.commit()


def test_each_kind_of_text_carries_its_own_typography(app):
    """The hero's heading, sub-heading, label, button and caption were wired to
    two shared buckets, so restyling one moved the others. Every role now emits
    its own variables and the CSS gives each one its own rules."""
    from app import TEXT_ROLES, TEXT_ROLE_PROPS
    from app.blueprints.admin import TEXT_ROLE_KEYS

    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "css"
    css = (root / "builder-parts.css").read_text(encoding="utf-8")
    bp = (root / "builder-bp.css").read_text(encoding="utf-8")

    for role in TEXT_ROLES:
        for prop, _unit in TEXT_ROLE_PROPS:
            var = "--pb-%s-%s" % (role, prop)
            # base + size breakpoints live in builder-parts; other md/lg in builder-bp
            if prop.endswith(("md", "lg")) and prop not in ("sizemd", "sizelg"):
                hay = bp
            else:
                hay = css
            assert '[style*="%s:"]' % var in hay, "no rule for " + var
            assert "style_%s_%s" % (role, prop) in TEXT_ROLE_KEYS, \
                "the editor cannot save style_%s_%s" % (role, prop)

    # composed shadows: base in parts, md/lg overrides in builder-bp
    for role in TEXT_ROLES:
        assert '[style*="--pb-%s-shadow:"]' % role in css
        assert '[style*="--pb-%s-shadowmd:"]' % role in bp
        assert '[style*="--pb-%s-shadowlg:"]' % role in bp

    # the roles must not overlap: a rule for one role may not also list a class
    # another role claims, or a change to one would still reach the other
    claims = {
        "title": ".ok-hero-title", "sub": ".ok-hero-sub", "body": ".ok-abt-body",
        "eyebrow": ".ok-hero-kicker", "cardtitle": ".ok-card-title",
        "cardtext": ".ok-card-text", "nav": ".nav-link",
    }
    for role, own in claims.items():
        line = next(l for l in css.splitlines()
                    if '[style*="--pb-%s-color:"]' % role in l and own in l)
        # the classes this rule CLAIMS are the ones before the exclusion list
        claimed = line.split(":not(", 1)[0]
        tokens = set(re.findall(r"\.[A-Za-z0-9_-]+", claimed))
        assert own in tokens, "%s's own hook went missing" % role
        for other, foreign in claims.items():
            if other == role:
                continue
            assert foreign not in tokens, \
                "%s's rule also claims %s (%s)" % (role, foreign, other)


def test_a_section_with_only_the_old_keys_is_untouched(app):
    """Nothing about the older whole-section keys changed, so a site styled
    before any of this renders exactly as it did."""
    with app.app_context():
        style = app.jinja_env.globals["pb_section_style"]
        legacy = style({"style_hsize": "52", "style_tcolor": "#333333"})
        assert "--pb-hsize:52px" in legacy
        assert "--pb-tcolor:#333333" in legacy
        assert "--pb-title-" not in legacy, "a legacy key leaked into a role"

        roled = style({"style_title_size": "44", "style_sub_size": "18",
                       "style_btn_family": "Georgia, serif"})
        assert "--pb-title-size:44px" in roled
        assert "--pb-sub-size:18px" in roled
        assert "--pb-btn-family:Georgia, serif" in roled
        assert "--pb-hsize" not in roled, "a role key leaked into the old bucket"


def test_a_refused_upload_never_clears_the_slot(app):
    """The bug this endpoint's guard exists for.

    inline_image used to fall through to the (empty) url field when it refused a
    file, which deleted the setting — so picking the wrong file type wiped the
    picture that was already there.
    """
    import io as _io
    from app.extensions import db
    from app.models.site import SiteSetting

    c = admin_client(app)
    with app.app_context():
        row = SiteSetting.query.filter_by(key="about_img").first()
        had = row.value if row else None
        if not row:
            db.session.add(SiteSetting(key="about_img", value="/static/img/uploads/keep-me.jpg"))
            db.session.commit()
    try:
        r = c.post("/admin/inline-image",
                   headers={"X-CSRF-Token": csrf(c, "/about")},
                   data={"key": "about_img",
                         "file": (_io.BytesIO(b"not really a document"), "notes.txt")},
                   content_type="multipart/form-data")
        assert r.status_code == 400, r.status_code
        payload = r.get_json()
        assert payload is not None, "the endpoint answered with a page, not JSON"
        assert not payload["ok"] and "not allowed" in payload["error"]
        with app.app_context():
            row = SiteSetting.query.filter_by(key="about_img").first()
            assert row is not None, "a refused file deleted the picture"
            assert row.value  # and left it pointing somewhere
    finally:
        with app.app_context():
            row = SiteSetting.query.filter_by(key="about_img").first()
            if had is None and row:
                db.session.delete(row)
            elif had is not None and row:
                row.value = had
            db.session.commit()


def test_site_images_sends_each_picture_on_its_own(app):
    """All 71 slots used to post as one upload, so one big file lost the lot.

    The client hit this for real: nginx turned away an 855 MB body four times.
    Each file input now uploads by itself, so no file input may carry a `name`
    that would put it back into the bulk form.
    """
    c = admin_client(app)
    html = c.get("/admin/site-images").get_data(as_text=True)
    file_inputs = re.findall(r"<input[^>]*type=\"file\"[^>]*>", html)
    assert file_inputs, "the page should still offer a file picker per slot"
    named = [tag for tag in file_inputs if re.search(r"\bname=", tag)]
    assert not named, "a named file input is back in the bulk form: %s" % named[:2]
    # and the mechanism that replaced it is actually wired up
    assert len(re.findall(r"data-slot=", html)) >= len(file_inputs)
    assert "/admin/inline-image" in html, "nothing sends the picture anywhere"

    # every slot's link box keeps its name: site_images_save() deletes the row
    # for any slot whose box arrives empty, so a missing name would clear it
    from app.blueprints.admin import SITE_IMAGE_SLOTS
    for _title, slots in SITE_IMAGE_SLOTS:
        for slot in slots:
            assert 'name="%s"' % slot[0] in html, slot[0]

    # Enter in a link box submits through the form's first submit button, and
    # every slot carries a Delete — so the first one must not be a delete
    body = html[html.index("<form"):]
    first_submit = re.search(r"<button[^>]*type=\"submit\"[^>]*>", body)
    assert first_submit, "the form has no submit button"
    assert "delete" not in first_submit.group(0).lower(), \
        "pressing Enter in a link box would delete a picture: %s" % first_submit.group(0)


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
        # every page the admin can restyle — the nine content pages plus the
        # three whose content is live data (menu, cart, locations)
        assert len(INNER_PAGES) == 12
        for spec in INNER_PAGES:
            html = c.get(spec["url"], follow_redirects=True).get_data(as_text=True)
            # the page's own sections, plus the header and footer every page
            # shares. The menu also emits one per live category, which is data
            # rather than registry, so it is a floor there rather than a count.
            floor = len(spec["sections"]) + 2
            found = html.count('class="pb-sec"')
            if spec["page"] == "menu":
                assert found >= floor, "%s: %d < %d" % (spec["page"], found, floor)
            else:
                assert found == floor, "%s: %d != %d" % (spec["page"], found, floor)
            assert 'data-section="header"' in html, spec["page"]
            assert 'data-section="footer"' in html, spec["page"]

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

    def text_fields(key):
        """Fields that render as words, so they become editable spans.

        A field whose value lands in an href is read with pc_attr and stays a
        plain string — wrapping it would put markup inside an attribute.
        """
        return [f for f in by_key[key]["fields"]
                if not f[0].endswith("_url") and not f[0].endswith("_href")
                and not f[0].endswith("_ph")]

    # the page's own copy, plus the footer and the chrome. The item sheet's
    # labels are in the chrome group too, but that sheet is fetched separately
    # when someone opens it, so it is not in this page's HTML.
    chrome = [f for f in text_fields("chrome") if not f[0].startswith("modal_")]
    # a nav label is on the page twice: the desktop bar and the mobile drawer
    # both render it, and editing either saves the same setting
    nav = [f for f in chrome if f[0].startswith("nav_")]
    expected = (len(text_fields("about")) + len(text_fields("footer"))
                + len(chrome) + len(nav))
    assert page.count('class="ok-ie"') == expected, (
        "expected %d editable strings, found %d"
        % (expected, page.count('class="ok-ie"')))
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


def test_switched_off_page_is_not_reachable(app, client):
    """Every feature switch removes its page URL, not just the nav link."""
    from app.extensions import db
    from app.models.site import SiteSetting

    def set_feature(slug, off):
        key = "feature_%s" % slug
        with app.app_context():
            row = SiteSetting.query.filter_by(key=key).first()
            if off and not row:
                db.session.add(SiteSetting(key=key, value="off"))
            elif off:
                row.value = "off"
            elif row:
                db.session.delete(row)
            db.session.commit()

    try:
        set_feature("catering", True)
        assert client.get("/catering").status_code == 404
        assert client.get("/about").status_code == 200
    finally:
        set_feature("catering", False)


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


def test_a_style_value_cannot_carry_anything_but_a_value(app):
    """A saved colour is a colour, not a way in.

    Two things read these strings back: the page, where a semicolon would end
    the declaration and let the rest become CSS every visitor gets, and the
    editor's own panel, where a quote would end the attribute and let the rest
    become attributes. Refused at the door, and refused again on the way out so
    anything already stored is inert too.
    """
    c = admin_client(app)
    tok = csrf(c, "/admin/design?page=about")

    for bad in ('red;position:fixed;inset:0',
                'red;background-image:url(http://evil.example/x.png)',
                'red" onfocus="alert(1)',
                'red</style><script>alert(1)</script>'):
        r = c.post("/admin/inline-style",
                   json={"page": "about", "section": "hero",
                         "key": "style_bg", "value": bad},
                   headers={"X-CSRF-Token": tok})
        assert r.status_code == 400, "stored a style value that is not one: %r" % bad

    # and the emitter refuses too, for whatever a previous version let through
    with app.app_context():
        style_of = app.jinja_env.globals["pb_section_style"]
        out = style_of({"style_bg": "red;position:fixed", "style_hcolor": "#123456"})
        assert "position" not in out
        assert "--pb-hcolor:#123456" in out, "a good value beside a bad one must survive"


def test_a_manager_pinned_to_one_shop_cannot_read_another(app, monkeypatch):
    """?store= is head office's switch, not a way around the pin.

    Tested at _admin_store() rather than through a screen because that one
    function decides the shop for every admin page there is — orders, the CSV
    export, the saved payment and SMS keys.
    """
    import app.blueprints.admin as admin_bp
    from app.models.store import Store

    with app.app_context():
        shops = Store.query.limit(2).all()
        if len(shops) < 2:
            pytest.skip("needs two shops to tell them apart")
        mine_id, theirs_slug = shops[0].id, shops[1].slug

    class Pinned(object):
        store_id = mine_id

    class HeadOffice(object):
        store_id = None

    monkeypatch.setattr(admin_bp, "current_user", lambda: Pinned())
    with app.test_request_context("/admin/orders?store=" + theirs_slug):
        assert admin_bp._admin_store().id == mine_id, \
            "?store= walked a pinned manager into another shop"

    monkeypatch.setattr(admin_bp, "current_user", lambda: HeadOffice())
    with app.test_request_context("/admin/orders?store=" + theirs_slug):
        assert admin_bp._admin_store().slug == theirs_slug, \
            "head office must still be able to switch shops"


def test_a_font_picked_on_a_custom_page_is_actually_fetched(app):
    """The picker previews a family by injecting it; a visitor gets only what
    the <head> asks for, so the two must agree."""
    from app.models.page import BuilderPage, PageSection

    with app.app_context():
        page = BuilderPage(slug="font-probe-page", title="Font probe",
                           html="<section data-dyn=\"hero\"></section>",
                           published=True)
        db.session.add(page)
        db.session.add(PageSection(page="p:font-probe-page", key="body",
                                   label="Body",
                                   config={"style_title_family": "'Playfair Display',serif"}))
        db.session.commit()
    try:
        html = app.test_client().get("/p/font-probe-page").get_data(as_text=True)
        assert "Playfair+Display" in html, \
            "the family this page chose was never requested from Google"
    finally:
        with app.app_context():
            PageSection.query.filter_by(page="p:font-probe-page").delete()
            BuilderPage.query.filter_by(slug="font-probe-page").delete()
            db.session.commit()


def test_no_screen_offers_a_reset_that_cannot_work(app):
    """A button that always 404s reads as a broken admin."""
    from app.models.page import INNER_PAGE_BY_KEY

    c = admin_client(app)
    for page in ("site",) + tuple(INNER_PAGE_BY_KEY)[:3]:
        html = c.get("/admin/design?page=" + page).get_data(as_text=True)
        action = "/admin/design/%s/reset-all" % page
        offered = action in html
        works = page in INNER_PAGE_BY_KEY
        assert offered == works, \
            "%s: reset button offered=%s but the route %s" % (
                page, offered, "exists" if works else "404s")


def test_no_control_moves_two_kinds_of_text_at_once(app):
    """The point of the whole per-element system.

    The old whole-section keys addressed text by tag: "Heading size" set h1/h2
    outright, h3 at 70% and h4-h6 at 58%, so one slider moved a section
    heading, its card headings and its sub-headings together. They still
    render for anything saved before, but nothing may offer or write them.
    """
    from app.blueprints.admin import (RETIRED_STYLE_FIELDS, DESIGN_FIELDS,
                                      TEXT_ROLE_KEYS, CTA_KEYS)

    offered = {f[0] for f in DESIGN_FIELDS} | TEXT_ROLE_KEYS | CTA_KEYS
    for key in RETIRED_STYLE_FIELDS:
        assert key not in offered, "%s is still offered on the design screen" % key

    panel = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
             / "partials" / "inline_editor.html").read_text(encoding="utf-8")
    canvas = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
              / "admin" / "canvas.html").read_text(encoding="utf-8")
    for key in RETIRED_STYLE_FIELDS:
        assert '"%s"' % key not in panel, "%s is still a control on the page" % key
        assert "'%s'" % key not in canvas, "%s is still a control in the canvas" % key

    # and the server refuses to write one
    c = admin_client(app)
    tok = csrf(c, "/admin/design?page=about")
    r = c.post("/admin/inline-style",
               json={"page": "home", "section": "hero",
                     "key": "style_hsize", "value": "80px"},
               headers={"X-CSRF-Token": tok})
    assert r.status_code == 400, "a retired whole-section key was accepted"


def test_the_hero_description_is_a_paragraph(app):
    """Semantics say what a thing is; the class says how it looks.

    It was an <h4>, which is why the tag-based size rule reached it at all.
    """
    hero = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
            / "website" / "sections" / "hero.html").read_text(encoding="utf-8")
    assert '<p class="ok-hero-sub"' in hero
    assert "<h4" not in hero, "the hero is using a heading tag for body text again"

    html = app.test_client().get("/").get_data(as_text=True)
    assert 'class="ok-hero-sub"' in html
    # exactly one h1 per slide, and the description is not one of them
    assert "<h4" not in html.split('data-hero')[1][:4000]


def test_a_page_only_carries_the_big_stylesheet_when_it_needs_it(app):
    """190 KB of selectors that anchor on p, a, span and h1-h6 have no business
    on a page that has not set one of their values."""
    from app.models.page import PageSection
    from app.extensions import db as _db

    c = app.test_client()
    plain = c.get("/about").get_data(as_text=True)
    assert "builder-parts.css" not in plain, \
        "an unstyled page is still downloading the per-element rules"

    # editing always needs them, because the panel writes those variables live
    admin = admin_client(app)
    assert "builder-parts.css" in admin.get("/about?edit=1").get_data(as_text=True)

    # and a page that has set one gets them
    with app.app_context():
        row = PageSection.query.filter_by(page="about").first()
        if row is None:
            pytest.skip("no about section to style")
        key, cfg = row.key, dict(row.config or {})
        row.config = dict(cfg, style_title_size="44px")
        _db.session.commit()
    try:
        assert "builder-parts.css" in c.get("/about").get_data(as_text=True), \
            "a styled page is missing the rules that style it"
    finally:
        with app.app_context():
            row = PageSection.query.filter_by(page="about", key=key).first()
            row.config = cfg
            _db.session.commit()


def test_the_editor_is_never_served_from_cache(app):
    """A tab left open across an update keeps running the editor it loaded.

    That is how the client ended up dragging a "Heading size" slider that no
    longer exists: the panel is inlined into the page, so the page must not be
    cacheable while editing.
    """
    c = admin_client(app)
    for path in ("/?edit=1", "/admin/design?page=about", "/admin/canvas"):
        r = c.get(path)
        assert "no-store" in (r.headers.get("Cache-Control") or ""), \
            "%s can be restored from cache" % path
    # ordinary visitors are unaffected
    plain = app.test_client().get("/about")
    assert "no-store" not in (plain.headers.get("Cache-Control") or "")


def test_an_old_setting_can_still_be_removed(app):
    """Retired keys render but are no longer offered. A section that carries one
    must not be stuck with it: setting is refused, clearing is allowed."""
    from app.models.page import PageSection
    from app.extensions import db as _db

    c = admin_client(app)
    tok = csrf(c, "/admin/design?page=about")

    with app.app_context():
        row = PageSection.query.filter_by(page="home", key="hero").first()
        assert row is not None
        before = dict(row.config or {})
        row.config = dict(before, style_hsize="80px")
        _db.session.commit()
    try:
        # setting one is still refused
        assert c.post("/admin/inline-style",
                      json={"page": "home", "section": "hero",
                            "key": "style_hsize", "value": "90px"},
                      headers={"X-CSRF-Token": tok}).status_code == 400
        # clearing it is not
        r = c.post("/admin/inline-style",
                   json={"page": "home", "section": "hero",
                         "key": "style_hsize", "value": ""},
                   headers={"X-CSRF-Token": tok})
        assert r.status_code == 200, r.get_data(as_text=True)
        with app.app_context():
            cfg = PageSection.query.filter_by(page="home", key="hero").first().config or {}
            assert "style_hsize" not in cfg, "the old setting could not be removed"
    finally:
        with app.app_context():
            row = PageSection.query.filter_by(page="home", key="hero").first()
            row.config = before
            _db.session.commit()


def test_the_panel_leads_with_the_text_controls(app):
    """People open the panel because they clicked on words."""
    panel = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
             / "partials" / "inline_editor.html").read_text(encoding="utf-8")
    build = panel[panel.index("function buildPanel"):]
    build = build[:build.index("dPanel.classList.add")]
    assert build.index("buildTextControls(el)") < build.index("CONTROLS.forEach"), \
        "the section controls come before the text controls again"


def test_the_preview_keeps_the_page_in_order(app):
    """The Visual editor showed the footer above every section.

    Its preview reorders the page to match the layer list, anchored on the
    first .pb-sec it finds. That stopped being the hero the day the header and
    footer became design targets of their own: the anchor became the header,
    whose parent is <body>, so every section was appended after the footer and
    the modals. The anchor has to be one of the page's own sections.
    """
    canvas = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
              / "admin" / "canvas.html").read_text(encoding="utf-8")
    sync = canvas[canvas.index("function syncOrder"):]
    sync = sync[:sync.index("\n  }")]
    assert "doc.querySelector('.pb-sec')" not in sync, \
        "the preview is anchored on the first .pb-sec again — that is the header"
    assert "layerKeys()" in sync and "el.parentNode === parent" in sync, \
        "sections must be reordered inside their own parent only"


def test_the_store_picker_stays_out_of_the_editor(app):
    """It opens over the whole page, and there is nothing to design behind it."""
    c = admin_client(app)
    for path in ("/?edit=1", "/?pbedit=1"):
        html = c.get(path).get_data(as_text=True)
        assert "OK.openLocation" not in html, "%s still opens the store picker" % path
    # a first-time visitor is still asked
    plain = app.test_client().get("/").get_data(as_text=True)
    assert ("OK.openLocation" in plain) or ("needs_location" not in plain)


def test_opening_hours_live_in_one_place(app):
    """Two screens edited the same seven rows; only Store settings does now."""
    shell = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
             / "layouts" / "admin_base.html").read_text(encoding="utf-8")
    assert "'/admin/hours'" not in shell, "the sidebar still has a second hours screen"
    assert "'Store settings'" in shell

    c = admin_client(app)
    r = c.get("/admin/hours")
    assert r.status_code in (301, 302)
    assert "/admin/settings" in r.headers["Location"]
    assert "#hours" in r.headers["Location"], "it must land on the hours tab"
    # and the tab that owns them is still there
    assert 'data-tab="hours"' in c.get("/admin/settings").get_data(as_text=True)


def test_no_editable_value_is_rendered_inside_a_tag(app):
    """In edit mode every text field is wrapped in a clickable <span>.

    A field a template puts inside an attribute must be left alone, or the tag
    closes early and the rest of it lands on the page as text — which is what
    happened to the Instagram reels grid: href=".../<span …>oksmashedburger…
    printed half the anchor on the page and killed the tiles.
    """
    import os
    import re

    from app.blueprints.website import _NON_TEXT

    tag_re = re.compile(r"<[a-zA-Z][^>]*>", re.S)
    cfg_re = re.compile(r"cfg\.get\(\s*['\"]([a-zA-Z0-9_]+)['\"]")
    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "templates" / "website"
    offenders = {}

    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            html = (pathlib.Path(dirpath) / name).read_text(encoding="utf-8")
            keys = set()
            for tag in tag_re.findall(html):
                keys.update(cfg_re.findall(tag))
                # a local set from cfg and then used in the tag counts too
                for local, key in re.findall(
                        r"\{%\s*set\s+(_?\w+)\s*=\s*cfg\.get\(\s*['\"](\w+)['\"]", html):
                    if re.search(r"\{\{\s*" + re.escape(local) + r"\b", tag):
                        keys.add(key)
            for key in keys:
                if not any(key.endswith(t) or key == t for t in _NON_TEXT):
                    offenders.setdefault(key, []).append(name)

    assert not offenders, (
        "these fields are rendered inside an attribute but are still wrapped "
        "for editing: " + ", ".join("%s (%s)" % (k, ", ".join(v))
                                    for k, v in sorted(offenders.items())))


def test_a_saved_style_never_leaves_a_stale_copy_behind(app):
    """After a save the panel replaces the section's own variables with the ones
    the server rebuilt. The browser writes a style attribute as "a: 1; b: 2", so
    the test that spots our variables has to trim first — without it every
    declaration after the first was kept and re-appended after the new values,
    where it wins. The heading-shadow controls are composed server-side and have
    no variable of their own, so they were the ones that visibly died."""
    panel = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
             / "partials" / "inline_editor.html").read_text(encoding="utf-8")
    assert 'p.trim().indexOf("--pb-")' in panel, \
        "the stale-declaration filter is comparing an untrimmed string again"


def test_choosing_a_colour_or_a_shadow_beats_the_hero_shimmer(app):
    """The hero's type is painted by a gradient clipped to its glyphs, with the
    shadow in a filter. A colour or a shadow the client chooses has to win."""
    css = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "css"
    parts = (css / "builder-parts.css").read_text(encoding="utf-8")
    base = (css / "builder.css").read_text(encoding="utf-8")

    colour_rule = next(l for l in parts.splitlines()
                       if '[style*="--pb-title-color:"]' in l and "color:var" in l)
    assert "-webkit-text-fill-color" in colour_rule, \
        "a chosen colour still loses to the shimmer's transparent text fill"

    shadow_rule = base[base.index('[style*="--pb-textshadow:"]'):]
    shadow_rule = shadow_rule[:shadow_rule.index("}")]
    assert "filter:none" in shadow_rule.replace(" ", ""), \
        "No shadow cannot remove the built-in drop-shadow"


def test_the_visual_editor_never_wipes_a_setting_it_cannot_see(app):
    """It only offers section-level things now.

    Its Save used to store the whole config it was holding, so a tab opened
    before someone styled a heading on the page would, on Save, delete that
    heading's settings — which is how a section lost the size the client had
    chosen for it.
    """
    from app.models.page import PageSection
    from app.extensions import db as _db

    c = admin_client(app)
    with app.app_context():
        row = PageSection.query.filter_by(page="home", key="catering").first()
        assert row is not None
        before = dict(row.config or {})
        row.config = dict(before, style_title_size="41px", style_bg="#ffffff")
        _db.session.commit()
    try:
        # a stale tab: it knows about the background, not the heading size
        r = c.post("/admin/canvas/save",
                   json={"sections": [{"key": "catering", "enabled": True,
                                       "config": {"style_bg": "#eeeeee"}}]},
                   headers={"X-CSRF-Token": csrf(c, "/admin/canvas")})
        assert r.status_code == 200
        with app.app_context():
            cfg = PageSection.query.filter_by(page="home", key="catering").first().config or {}
        assert cfg.get("style_title_size") == "41px", \
            "the Visual editor wiped a setting from another screen"
        assert cfg.get("style_bg") == "#eeeeee", "its own control did not save"
    finally:
        with app.app_context():
            row = PageSection.query.filter_by(page="home", key="catering").first()
            row.config = before
            _db.session.commit()


def test_a_shadow_belongs_to_one_kind_of_text(app):
    """It used to be one control for the whole section: the same shadow landed
    on every h1-h6, p, li, span and link at once — the client's own complaint,
    in the one place it was still true."""
    from app import TEXT_ROLES
    from app.blueprints.admin import (RETIRED_STYLE_FIELDS, TEXT_ROLE_KEYS,
                                      DESIGN_FIELDS)

    for key in ("style_tsside", "style_tsdist", "style_tsblur", "style_tscolor"):
        assert key in RETIRED_STYLE_FIELDS, "%s is still a section-wide control" % key
        assert key not in {f[0] for f in DESIGN_FIELDS}

    for role in TEXT_ROLES:
        for prop in ("tsside", "tsdist", "tsblur", "tscolor"):
            assert "style_%s_%s" % (role, prop) in TEXT_ROLE_KEYS, \
                "%s has no shadow of its own" % role

    css = (pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "css"
           / "builder-parts.css").read_text(encoding="utf-8")
    for role in TEXT_ROLES:
        assert '[style*="--pb-%s-shadow:"]' % role in css, role

    # and one role's shadow really is composed on its own
    with app.app_context():
        style_of = app.jinja_env.globals["pb_section_style"]
        out = style_of({"style_title_tsside": "bottom", "style_title_tsdist": "6",
                        "style_sub_tsside": "none"})
        out2 = style_of({"style_title_tsside": "none",
                         "style_title_tssidelg": "bottom", "style_title_tsdistlg": "8"})
    assert "--pb-title-shadow:0px 6px 4px" in out, out
    assert "--pb-sub-shadow:none" in out, out
    assert "--pb-textshadow" not in out, "the old section-wide value came back"
    assert "--pb-title-shadow:none" in out2
    assert "--pb-title-shadowlg:0px 8px" in out2


def test_every_card_control_reaches_every_kind_of_card(app):
    """The tiles, the location cards and the Google review cards.

    Only .ok-card was named, so on the Locations section the whole Cards group
    did nothing — the client has a card background saved there right now and
    had never seen it take effect.
    """
    css = (pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "css"
           / "builder.css").read_text(encoding="utf-8")
    misses = []
    for var in ("cardbg", "cardborder", "cardborderw", "cardhead", "cardtext",
                "cardradius", "cardpad", "cardw", "cardh", "cardminw", "shadow"):
        for line in css.splitlines():
            if '[style*="--pb-%s:"]' % var in line and ".ok-card" in line:
                if ".ok-loccard" not in line or ".ok-gcard" not in line:
                    misses.append(var)
                break
    assert not misses, "these card controls only reach .ok-card: %s" % sorted(set(misses))


def test_the_extra_picture_can_be_put_above_the_section(app):
    """"Where it goes: Above" used to hide the picture and show nothing.

    It swapped to an empty ::before, and the position was never even emitted,
    so the control had nothing on the other end of it either.
    """
    with app.app_context():
        style_of = app.jinja_env.globals["pb_section_style"]
        below = style_of({"style_xtraimg": "/static/img/logo.png"})
        above = style_of({"style_xtraimg": "/static/img/logo.png",
                          "style_xtrapos": "top"})
    assert "--pb-xtraimg:url(" in below
    assert "--pb-xtraorder" not in below, "below is the default and needs no order"
    assert "--pb-xtraorder:0" in above, "Above the section emits nothing"

    css = (pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "css"
           / "builder.css").read_text(encoding="utf-8")
    assert '[style*="--pb-xtrapos:top"]::before' not in css, \
        "the empty ::before that swallowed the picture is back"
    block = css[css.index('[style*="--pb-xtraimg:"]::after'):]
    block = block[:block.index("}")]
    assert "margin:var(--pb-xtraalign" in block.replace(" ", ""), \
        "alignment is a margin shorthand; margin-inline throws half of it away"
