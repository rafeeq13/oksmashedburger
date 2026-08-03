"""Admin-managed page layout (a light CMS / page-builder foundation).

Each storefront section is a `PageSection` row: it can be reordered, shown/hidden
and have its key text overridden from the admin. Templates render sections in
`sort_order`, skipping disabled ones, and read text overrides from `config`
(falling back to the built-in default when a field isn't set)."""
import re
from app.extensions import db


class BuilderPage(db.Model):
    """A standalone page built visually with GrapesJS (drag-drop widgets:
    buttons, forms, text, images, columns). Stored as rendered html + css plus
    the GrapesJS project JSON (`gjs`) for re-editing. Served at /p/<slug>."""
    __tablename__ = "builder_pages"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, index=True, nullable=False)
    title = db.Column(db.String(200), default="Untitled page")
    html = db.Column(db.Text, default="")
    css = db.Column(db.Text, default="")
    gjs = db.Column(db.JSON, default=dict)          # GrapesJS project data
    published = db.Column(db.Boolean, default=True, nullable=False)
    show_in_nav = db.Column(db.Boolean, default=False, nullable=False)
    is_home = db.Column(db.Boolean, default=False, nullable=False)   # this page IS the "/" home
    override_path = db.Column(db.String(120), index=True)  # storefront path this page replaces (/about …)
    meta_title = db.Column(db.String(200))          # SEO <title> override
    meta_description = db.Column(db.String(300))     # SEO meta description
    head_code = db.Column(db.Text)                   # custom <head> code (meta/CSS/JS)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


# Built-in home sections that can be dropped into the builder as live blocks.
DYNAMIC_SECTION_KEYS = [
    "hero", "explore_menu", "best_sellers", "how_it_works", "catering",
    "about", "reviews", "locations", "franchise", "testimonials", "instagram",
]


def slugify(text, fallback="page"):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or fallback


def unique_page_slug(text):
    base = slugify(text)
    slug, n = base, 2
    while BuilderPage.query.filter_by(slug=slug).first():
        slug = "%s-%d" % (base, n); n += 1
    return slug


class PageSection(db.Model):
    __tablename__ = "page_sections"
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String(40), default="home", index=True)   # future: other pages
    key = db.Column(db.String(60), index=True, nullable=False)
    label = db.Column(db.String(120))
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    config = db.Column(db.JSON, default=dict)     # text/style overrides only
    __table_args__ = (db.UniqueConstraint("page", "key", name="uq_page_key"),)


# Hero carousel slide copy (title, sub-text). Kept in step with the same list in
# templates/website/sections/hero.html (that file holds these as the fallback).
HERO_SLIDES = [
    ("Real smashed burgers, served fast.", "Fresh-smashed, deal-forward, and tracked to your door. Delivery or pickup, you decide."),
    ("Double the smash, double the joy.", "Two fresh-smashed patties, melty American cheese and our toasted bun."),
    ("Loaded fries, zero regrets.", "Crispy, cheesy and piled high, the perfect sidekick to any smash."),
    ("Hand-spun shakes, thick and cold.", "Vanilla, chocolate and more, blended fresh to order."),
    ("Turn up the heat.", "The Spicy Jalapeno Smash brings fresh jalapenos and a kick you will love."),
    ("Crispy chicken, done right.", "Golden, crunchy and stacked tall on a toasted bun."),
    ("Plant-based and proud.", "The Garden Vegan Smash, all the flavor with none of the compromise."),
    ("Delivery or pickup.", "You choose how you want it, we smash it fresh either way."),
    ("From kitchen to doorstep.", "Follow your order live, every step from the flat-top to your door."),
    ("Deals that hit different.", "Free delivery on your first order with code OKFIRST."),
]
_hero_fields = [("eyebrow", "Eyebrow label", "Craft Smashed Burgers"),
                ("cta_text", "Button text", "Start Your Order")]
for _i, (_t, _x) in enumerate(HERO_SLIDES, 1):
    _hero_fields.append(("slide%d_title" % _i, "Slide %d title" % _i, _t))
    _hero_fields.append(("slide%d_text" % _i, "Slide %d text" % _i, _x))


# Registry of the home page's sections: the canonical order, human label, which
# text fields the admin may override, an optional theme choice, and the built-in
# default text (used as the admin field placeholder; templates hold the same
# fallback). `config` on a row stores ONLY overrides — empty means "use default".
HOME_SECTIONS = [
    {"key": "hero", "label": "Hero carousel", "theme": False, "fields": _hero_fields},
    {"key": "explore_menu", "label": "Explore the menu", "theme": True,
     "fields": [("heading", "Heading", "Explore the Menu"),
                ("cta_text", "Button text", "See full menu"),
                ("cta_href", "Button link", "/menu")]},
    {"key": "best_sellers", "label": "Best sellers", "theme": True,
     "fields": [("heading", "Heading", "Best Sellers"),
                ("cta_text", "Link text", "See full menu"),
                ("cta_href", "Link URL", "/menu")]},
    {"key": "how_it_works", "label": "How it works", "theme": True,
     "fields": [("heading", "Heading", "From tap to table in 4 steps"),
                ("step1_title", "Step 1 title", "1 · Pick a store"),
                ("step1_desc", "Step 1 text", "Set delivery or pickup."),
                ("step2_title", "Step 2 title", "2 · Build your order"),
                ("step2_desc", "Step 2 text", "Customize burgers & combos."),
                ("step3_title", "Step 3 title", "3 · Fast checkout"),
                ("step3_desc", "Step 3 text", "Cards, wallets, gift cards & points."),
                ("step4_title", "Step 4 title", "4 · Track live"),
                ("step4_desc", "Step 4 text", "Kitchen-to-doorstep tracking."),
                ("cta_text", "Button text", "Order Now"),
                ("cta_href", "Button link", "/menu")]},
    {"key": "catering", "label": "Catering banner", "theme": False,
     "fields": [("heading", "Heading", "Catering for any event"),
                ("subheading", "Sub-text", "From team breakfasts to weekend gatherings, we bring fresh-smashed burgers, loaded sides, and crowd-pleasing favorites straight to your event."),
                ("cta_text", "Button text", "See catering"),
                ("cta_href", "Button link", "/catering")]},
    {"key": "about", "label": "About the brand", "theme": False,
     "fields": [("heading", "Heading", "Learn all about the {brand} magic"),
                ("subheading", "Paragraph 1", "{brand} is a fast-casual smash-burger concept built on a simple belief: people deserve something better. Quality ingredients, cooked to order, handcrafted, consistent, and served with a smile."),
                ("body2", "Paragraph 2", "We're obsessed with the details, that's why we smash every patty fresh on the flat-top, toast our buns, make our sauces in-house, and never let a burger sit. Delivery or pickup, you get the same OK-good burger every time."),
                ("cta_text", "Button text", "Know us better"),
                ("cta_href", "Button link", "/about")]},
    {"key": "reviews", "label": "Ratings / reviews", "theme": True,
     "fields": [("heading", "Heading", "What the people think")]},
    {"key": "locations", "label": "Locations near you", "theme": True,
     "fields": [("heading", "Heading", "Locations near you"),
                ("cta_text", "Button text", "See all locations"),
                ("cta_href", "Button link", "/locations")]},
    {"key": "franchise", "label": "Franchise", "theme": False,
     "fields": [("heading", "Heading", "Franchise Opportunities"),
                ("subheading", "Sub-text", "As a franchise partner, you gain proven recipes, operational support, streamlined systems, and a beloved concept built for all-day demand."),
                ("cta_text", "Button text", "Learn more"),
                ("cta_href", "Button link", "/contact")]},
    {"key": "testimonials", "label": "Customer testimonials", "theme": True,
     "fields": [("heading", "Heading", "What locals have to say")]},
    {"key": "instagram", "label": "Instagram feed", "theme": True,
     "fields": [("heading", "Heading", "Follow us on Instagram"),
                ("handle", "Instagram handle", "oksmashedburger"),
                ("tagline", "Profile tagline", "Real smashed burgers, fast · Philadelphia · Find your nearest location ↓"),
                ("cta_text", "Follow button text", "Follow @oksmashedburger")]},
]

# Background themes offered for sections that support a style choice. ("dark" is
# only honoured by custom blocks; built-in sections ignore it and stay default.)
SECTION_THEMES = [
    ("default", "Default"),
    ("cream", "Cream / soft yellow"),
    ("white", "Plain white"),
    ("dark", "Dark"),
]

# Fields for an admin-added CUSTOM block (rendered by sections/custom.html).
CUSTOM_FIELDS = [
    ("heading", "Heading", ""),
    ("subheading", "Sub-text", ""),
    ("cta_text", "Button text", ""),
    ("cta_href", "Button link", ""),
    ("image", "Image URL", ""),
]


def is_custom_key(key):
    return bool(key) and key.startswith("custom_")


def spec_for(key):
    """Field/theme spec for a section key — a registry entry, or a synthetic
    spec for an admin-added custom block."""
    for s in HOME_SECTIONS:
        if s["key"] == key:
            return s
    return {"key": key, "label": "Custom block", "theme": True,
            "fields": CUSTOM_FIELDS, "custom": True}


def next_custom_key():
    existing = {s.key for s in PageSection.query.filter_by(page="home").all()}
    n = 1
    while ("custom_%d" % n) in existing:
        n += 1
    return "custom_%d" % n


# ── Other storefront pages: editable headline copy (stored as SiteSetting keys,
#    read by templates via the injected `site` dict → site.get(key) or default) ──
PAGE_CONTENT = [
    {"key": "about", "label": "About", "url": "/about", "fields": [
        ("about_hero_heading", "Hero heading", "Smashed the right way."),
        ("about_hero_text", "Hero sub-text", "We started with one griddle, one sauce recipe and one belief: a great smash burger should be fresh, fast and fair. That belief still fires up every OK kitchen across Philadelphia."),
        ("about_story_heading", "Story section heading", "From a corner griddle to four neighborhood kitchens"),
        ("about_values_heading", "Values section heading", "What we stand for"),
        ("about_team_heading", "Team section heading", "Meet the team"),
        ("about_cta_heading", "Closing CTA heading", "Hungry yet?")]},
    {"key": "contact", "label": "Contact", "url": "/contact", "fields": [
        ("contact_hero_heading", "Hero heading", "Get in touch"),
        ("contact_hero_text", "Hero sub-text", "Questions, catering, franchising or just some love for the OK sauce, we read every message and reply fast."),
        ("contact_faq_heading", "FAQ teaser heading", "Quick answers, no waiting")]},
    {"key": "catering", "label": "Catering", "url": "/catering", "fields": [
        ("catering_hero_heading", "Hero heading", "Catering for any event."),
        ("catering_hero_text", "Hero sub-text", "From team lunches to weekend gatherings, we bring fresh-smashed burgers, loaded sides and crowd-pleasing favorites straight to your event."),
        ("catering_cater_heading", "What-we-cater heading", "What we cater"),
        ("catering_packages_heading", "Packages heading", "Catering packages"),
        # catering_how_heading lived here until the "How catering works" section
        # was removed from the page; the field had nothing left to drive.
        ("catering_quote_heading", "Quote form heading", "Request a catering quote")]},
    {"key": "careers", "label": "Careers", "url": "/careers", "fields": [
        ("careers_hero_heading", "Hero heading", "Join our team."),
        ("careers_hero_text", "Hero sub-text", "Grill cooks, shift leads, drivers and managers. If you love good food and moving fast, we want to meet you. No restaurant experience required."),
        ("careers_why_heading", "Why-work heading", "Why work at {brand}"),
        ("careers_roles_heading", "Open-roles heading", "Open roles"),
        ("careers_apply_heading", "Apply form heading", "Apply now")]},
    {"key": "faq", "label": "FAQ / Help", "url": "/faq", "fields": [
        ("faq_hero_heading", "Hero heading", "How can we help?"),
        ("faq_hero_text", "Hero sub-text", "Search our help center or browse the topics below. Most answers are just a tap away."),
        ("faq_list_heading", "FAQ list heading", "Frequently asked"),
        ("faq_help_heading", "Still-need-help heading", "Still need help?")]},
    {"key": "deals", "label": "Deals", "url": "/deals", "fields": [
        ("deals_hero_heading", "Hero heading", "Deals & Offers"),
        ("deals_hero_text", "Hero sub-text", "Save on smashed favorites. Start an order straight from any deal, most need no code at all."),
        ("deals_list_heading", "Deals list heading", "All deals")]},
    {"key": "rewards", "label": "Rewards", "url": "/rewards", "fields": [
        ("rewards_hero_heading", "Hero heading", "Every bite earns you free food."),
        ("rewards_hero_text", "Hero sub-text", "Rack up points on every order and cash them in for burgers, sides and shakes. Plus birthday treats, referral bonuses and members-only deals."),
        ("rewards_earn_heading", "Earn & redeem heading", "Earn & redeem"),
        ("rewards_tiers_heading", "Membership tiers heading", "Membership tiers"),
        ("rewards_faq_heading", "Rewards FAQ heading", "Rewards FAQ")]},
    {"key": "giftcards", "label": "Gift cards", "url": "/gift-cards", "fields": [
        ("giftcards_hero_heading", "Hero heading", "Give the gift of a smash"),
        ("giftcards_hero_text", "Hero sub-text", "Delivered instantly by email or scheduled for the perfect moment. Any amount, redeemable on everything we make."),
        ("giftcards_build_heading", "Build-card heading", "Build your gift card"),
        ("giftcards_how_heading", "How-it-works heading", "How it works"),
        ("giftcards_corporate_heading", "Corporate heading", "Corporate & bulk gift cards")]},
]


def page_content_defaults(brand=""):
    """Flat {key: default_text} for every editable page-content field, with
    {brand} resolved (used for pre-fill and to detect unchanged saves)."""
    out = {}
    for p in PAGE_CONTENT:
        for k, _l, d in p["fields"]:
            out[k] = (d or "").replace("{brand}", brand)
    return out


def resolved_defaults(brand=""):
    """Effective default text for every section field, with {brand} filled in.
    Used to PRE-FILL the admin Page Builder inputs with the current copy and to
    detect "unchanged" saves (so a value equal to the default isn't stored as an
    override). Note: catering/franchise headings render with a <br> line break in
    the template; the plain default here is what the admin sees and edits."""
    out = {}
    for spec in HOME_SECTIONS:
        out[spec["key"]] = {f: (d or "").replace("{brand}", brand) for f, _l, d in spec["fields"]}
    return out


def home_sections_ordered():
    """Return the home sections as ORM rows in saved order, creating any missing
    rows from the registry on first use so the page always renders in full."""
    existing = {s.key: s for s in PageSection.query.filter_by(page="home").all()}
    changed = False
    for i, spec in enumerate(HOME_SECTIONS):
        if spec["key"] not in existing:
            row = PageSection(page="home", key=spec["key"], label=spec["label"],
                              enabled=True, sort_order=i, config={})
            db.session.add(row)
            existing[spec["key"]] = row
            changed = True
    if changed:
        db.session.commit()
    # All home rows in saved order: registry sections + admin-added custom blocks.
    registry_keys = {s["key"] for s in HOME_SECTIONS}
    rows = [r for r in existing.values()
            if r.key in registry_keys or is_custom_key(r.key)]
    rows.sort(key=lambda r: (r.sort_order, r.id))
    return rows
