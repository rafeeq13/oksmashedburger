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


# ── Other storefront pages: editable copy ────────────────────────────────────
# Stored as SiteSetting rows and read by the templates through the `pc()` Jinja
# global, so THIS registry is the single source of truth for the default text.
# (Templates used to repeat the default inline, and About's had drifted so far
# that the admin screen pre-filled copy that was nowhere on the page.)
#
# A field is (key, label, default) or (key, label, default, "area") when it is
# long enough to want a textarea in the admin.
PAGE_CONTENT = [
    {"key": "about", "label": "About", "url": "/about", "fields": [
        ("about_hero_heading", "Hero heading", "About Us"),
        ("about_story_heading", "Intro heading", "Start the day off right with one of our delicious smash burgers"),
        ("about_hero_text", "Intro paragraph", "{brand} is a fast-casual smash-burger concept built on a simple belief: people deserve something better. Quality ingredients, made from scratch, freshly cooked, handcrafted, consistent, and served with a smile.", "area"),
        ("about_card1_heading", "Card 1 heading", "Cooked Fresh And From Scratch"),
        ("about_card1_text", "Card 1 text", "We're passionate about the quality and consistency of our food, which is why we cook everything fresh and from scratch. We make our sauces in-house, hand-form every patty, toast our own buns, and never let a burger sit.", "area"),
        ("about_card2_heading", "Card 2 heading", "Community Focused And Locally-sourced"),
        ("about_card2_text", "Card 2 text", "We love the communities we're in, so much that we source our ingredients from local businesses: our beef, our produce and our bakery buns all come from partners right here in Philadelphia.", "area"),
        ("about_table_heading", "Table section heading", "Meet Us At The Table"),
        ("about_table_text", "Table paragraph 1", "We'll be playing upbeat music to set the vibes, pouring hand-spun shakes, cold-pressed lemonade and fresh soda.", "area"),
        ("about_table_text2", "Table paragraph 2", "We're excited to be able to start your day off right and we hope to serve you soon!", "area"),
        ("about_values_heading", "Band heading", "Different smashes for different folks"),
        ("about_values_text", "Band paragraph", "We are the lunch crowd, the late-night crew, the family Fridays and the game-day groups, serving different smashes for different folks.", "area"),
        ("about_team_heading", "Story section heading", "How it all started"),
        ("about_team_text", "Story paragraph 1", "In 2021, two friends set up a single flat-top in a Fishtown pop-up with one idea: press a ball of fresh beef hard onto a screaming-hot griddle, let the edges lace and caramelize, and serve it before it ever had a chance to cool down. The line went around the block by week two.", "area"),
        ("about_team_text2", "Story paragraph 2", "Four neighborhood kitchens later, nothing about the craft has changed. What's new is the tech that gets it to you faster: live tracking, easy reorders and rewards on every bite.", "area"),
        ("about_reviews_heading", "Reviews section heading", "What locals have to say"),
        ("about_ig_heading", "Instagram heading", "Follow us on Instagram"),
        ("about_ig_tagline", "Instagram tagline", "Real smashed burgers, fast · Philadelphia · Find your nearest location"),
        ("about_cta_heading", "Closing CTA heading", "Hungry yet?"),
        ("about_cta_text", "Closing CTA text", "Pick your kitchen, build your order and we'll smash it fresh.", "area")]},
    {"key": "contact", "label": "Contact", "url": "/contact", "fields": [
        ("contact_hero_heading", "Hero heading", "Get in touch"),
        ("contact_hero_text", "Hero sub-text", "Questions, catering, franchising or just some love for the OK sauce, we read every message and reply fast.", "area"),
        ("contact_form_heading", "Form heading", "Drop us a line"),
        ("contact_form_text", "Form sub-text", "Fill out the form and our team will get back to you within one business day.", "area"),
        ("contact_email_note", "Email card note", "We reply within 1 business day"),
        ("contact_hq_name", "HQ name", "OK Smashed Burger HQ"),
        ("contact_hq_address", "HQ address", "1201 Frankford Ave, Philadelphia · 19125"),
        ("contact_faq_heading", "FAQ teaser heading", "Quick answers, no waiting"),
        ("contact_faq_text", "FAQ teaser text", "A lot of questions have instant answers in our help center. Jump straight to a topic.", "area")]},
    {"key": "catering", "label": "Catering", "url": "/catering", "fields": [
        ("catering_hero_heading", "Hero heading", "Catering for any event."),
        ("catering_hero_text", "Hero sub-text", "From team lunches to weekend gatherings, we bring fresh-smashed burgers, loaded sides and crowd-pleasing favorites straight to your event.", "area"),
        ("catering_cater_heading", "What-we-cater heading", "What we cater"),
        ("catering_cater_text", "What-we-cater sub-text", "Every order is smashed fresh the morning of your event and delivered hot, labelled and ready to serve.", "area"),
        ("catering_card1_heading", "Card 1 heading", "Office lunches"),
        ("catering_card1_text", "Card 1 text", "Team meetings, client days and Friday treats. Individually boxed so everyone gets exactly what they ordered.", "area"),
        ("catering_card2_heading", "Card 2 heading", "Parties & celebrations"),
        ("catering_card2_text", "Card 2 text", "Birthdays, graduations and backyard get-togethers. Served as build-your-own trays or ready-to-eat boxes.", "area"),
        ("catering_card3_heading", "Card 3 heading", "Game day & groups"),
        ("catering_card3_text", "Card 3 text", "Sliders, loaded fries and shareable sides built for a crowd watching the game.", "area"),
        ("catering_packages_heading", "Packages heading", "Catering packages"),
        ("catering_packages_text", "Packages sub-text", "Pick a package or tell us what you need and we will build one for you.", "area"),
        ("catering_packages_note", "Packages small print", "Prices are a guide only. Final quotes depend on headcount, menu and location.", "area"),
        ("catering_quote_heading", "Quote form heading", "Request a catering quote"),
        ("catering_quote_text", "Quote form sub-text", "Tell us about your event and we will get back to you within one business day.", "area")]},
    {"key": "careers", "label": "Careers", "url": "/careers", "fields": [
        ("careers_hero_heading", "Hero heading", "Join our team."),
        ("careers_hero_text", "Hero sub-text", "Grill cooks, shift leads, drivers and managers. If you love good food and moving fast, we want to meet you. No restaurant experience required.", "area"),
        ("careers_why_heading", "Why-work heading", "Why work at {brand}"),
        ("careers_why_text", "Why-work sub-text", "We are a small, growing crew. That means real training, real hours and a real path to running your own kitchen.", "area"),
        ("careers_perk1_heading", "Perk 1 heading", "Fair pay, paid weekly"),
        ("careers_perk1_text", "Perk 1 text", "Above-minimum starting rates, tips shared across the whole crew.", "area"),
        ("careers_perk2_heading", "Perk 2 heading", "Flexible shifts"),
        ("careers_perk2_text", "Perk 2 text", "Schedules posted two weeks ahead, built around school and family.", "area"),
        ("careers_perk3_heading", "Perk 3 heading", "Train and grow"),
        ("careers_perk3_text", "Perk 3 text", "Most of our shift leads started on the griddle with zero experience.", "area"),
        ("careers_perk4_heading", "Perk 4 heading", "Free shift meal"),
        ("careers_perk4_text", "Perk 4 text", "A burger on us every shift, plus a discount on your days off.", "area"),
        ("careers_roles_heading", "Open-roles heading", "Open roles"),
        ("careers_apply_heading", "Apply form heading", "Apply now"),
        ("careers_apply_text", "Apply form sub-text", "Send us a note. No CV required for kitchen and counter roles, just tell us about yourself.", "area")]},
    {"key": "faq", "label": "FAQ / Help", "url": "/faq", "fields": [
        ("faq_hero_heading", "Hero heading", "How can we help?"),
        ("faq_hero_text", "Hero sub-text", "Search our help center or browse the topics below. Most answers are just a tap away.", "area"),
        ("faq_list_heading", "FAQ list heading", "Frequently asked"),
        ("faq_help_heading", "Still-need-help heading", "Still need help?"),
        ("faq_help_text", "Still-need-help text", "Can't find what you're looking for? Our Philly-based support team is quick, friendly and ready to sort it out.", "area")]},
    {"key": "news", "label": "News", "url": "/news", "fields": [
        ("news_hero_heading", "Hero heading", "News & updates."),
        ("news_hero_text", "Hero sub-text", "New openings, menu drops and everything happening across our Philadelphia kitchens.", "area"),
        ("news_cta_heading", "Closing CTA heading", "Hungry yet?"),
        ("news_cta_text", "Closing CTA text", "Fresh-smashed, deal-forward and tracked to your door. Build your order and taste why Philly keeps coming back.", "area")]},
    {"key": "deals", "label": "Deals", "url": "/deals", "fields": [
        ("deals_hero_heading", "Hero heading", "Deals & Offers"),
        ("deals_hero_text", "Hero sub-text", "Save on smashed favorites. Start an order straight from any deal, most need no code at all.", "area"),
        ("deals_list_heading", "Deals list heading", "All deals"),
        ("deals_empty_text", "Empty-state text", "No active deals right now, check back soon!")]},
    {"key": "rewards", "label": "Rewards", "url": "/rewards", "fields": [
        ("rewards_hero_heading", "Hero heading", "Every bite earns you free food."),
        ("rewards_hero_text", "Hero sub-text", "Rack up points on every order and cash them in for burgers, sides and shakes. Plus birthday treats, referral bonuses and members-only deals.", "area"),
        ("rewards_earn_heading", "Earn & redeem heading", "Earn & redeem"),
        ("rewards_stack_heading", "Stack-points card heading", "Ready to stack points?"),
        ("rewards_stack_text", "Stack-points card text", "Start an order now and watch your balance grow.", "area"),
        ("rewards_tiers_heading", "Membership tiers heading", "Membership tiers"),
        ("rewards_tiers_text", "Membership tiers sub-text", "The more you order, the more you unlock. Tiers are based on points earned in a calendar year.", "area"),
        ("rewards_referral_heading", "Referral heading", "Give $5, get $5"),
        ("rewards_referral_text", "Referral text", "Share your personal code. When a friend places their first order, they get $5 off, and you get $5 too. No limit on how many friends you invite.", "area"),
        ("rewards_faq_heading", "Rewards FAQ heading", "Rewards FAQ")]},
    {"key": "giftcards", "label": "Gift cards", "url": "/gift-cards", "fields": [
        ("giftcards_hero_heading", "Hero heading", "Give the gift of a smash"),
        ("giftcards_hero_text", "Hero sub-text", "Delivered instantly by email or scheduled for the perfect moment. Any amount, redeemable on everything we make.", "area"),
        ("giftcards_hero_note", "Hero small print", "Never expires · Redeemable online & in-store · Delivered in seconds"),
        ("giftcards_build_heading", "Build-card heading", "Build your gift card"),
        ("giftcards_balance_text", "Balance-check text", "Enter the 12-digit code from your gift card email to see the remaining balance.", "area"),
        ("giftcards_how_heading", "How-it-works heading", "How it works"),
        ("giftcards_corporate_heading", "Corporate heading", "Corporate & bulk gift cards"),
        ("giftcards_corporate_text", "Corporate text", "Reward your team or thank your clients. Order gift cards in bulk with custom branding, volume discounts and a single invoice. Our team will help you set it up.", "area")]},
    {"key": "locations", "label": "Locations", "url": "/locations", "fields": [
        ("locations_hero_heading", "Hero heading", "Find your OK Smashed Burger"),
        ("locations_search_placeholder", "Search placeholder", "Filter by area, address or ZIP")]},
]


def page_content_defaults(brand=""):
    """Flat {key: default_text} for every editable page-content field, with
    {brand} resolved (used for pre-fill, for `pc()` and to detect unchanged
    saves so a value equal to the default is never stored as an override)."""
    out = {}
    for p in PAGE_CONTENT:
        for f in p["fields"]:
            out[f[0]] = (f[2] or "").replace("{brand}", brand)
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
