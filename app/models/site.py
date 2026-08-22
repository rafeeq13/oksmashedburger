"""Brand-wide site content the admin can edit — e.g. the images shown in each
storefront section (hero slides, catering banner, about photo, …).

Stored as simple key/value rows; templates read them via the `site` context
variable and fall back to the built-in default when a key isn't set."""
from app.extensions import db


class SiteSetting(db.Model):
    __tablename__ = "site_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, index=True, nullable=False)
    value = db.Column(db.Text)


# Built-in default image for every editable slot. This is the single source of
# truth: storefront templates AND the admin "Site images" previews both read it,
# so an un-overridden slot always shows the picture the site is actually using.
# Keep the hero_* URLs in step with the `hero_slides` list in website/index.html.
# ── Feature switches ────────────────────────────────────────────────────────
# Whole parts of the storefront the client can turn off. A switch that has
# never been touched has no row, and no row means ON — turning the system on
# must not silently remove anything that is live today.
#
# (key, label, what disappears when it is off)
FEATURES = [
    ("feature_menu", "Menu",
     "The Menu page, item pages (/item/…), and Menu links in the header and footer."),
    ("feature_locations", "Locations",
     "The store locator page and its header/footer links."),
    ("feature_deals", "Deals & offers",
     "The Deals page, its nav and footer links, the promo-code box in the cart "
     "and at checkout, and the “Deals” badge in the menu."),
    ("feature_rewards", "Rewards & points",
     "The Rewards page, its nav, footer and account links, and points earning "
     "or spending anywhere in checkout."),
    ("feature_giftcards", "Gift cards",
     "The Gift cards page, its nav and footer links, and the gift-card box at "
     "checkout."),
    ("feature_catering", "Catering",
     "The Catering page and its header nav link."),
    ("feature_about", "About",
     "The About page and its header nav link."),
    ("feature_contact", "Contact",
     "The Contact page, footer links, and the contact form."),
    ("feature_careers", "Careers / Join our team",
     "The Careers page and its link in the More menu."),
    ("feature_faq", "Help / FAQ",
     "The FAQ page and the help links in the footer."),
    ("feature_news", "News & updates",
     "The News page and its nav and footer links."),
    ("feature_tracking", "Order tracking",
     "The Track Order page and its footer link."),
]

FEATURE_KEYS = [f[0] for f in FEATURES]


def features_from(settings):
    """{'deals': True, …} from a {key: value} map of SiteSetting rows.

    Absent or anything other than the string "off" reads as on, so a missing
    row — and a row written by some older version of the admin — both keep the
    feature visible rather than hiding a page nobody meant to hide.
    """
    return {k.replace("feature_", ""): (settings.get(k) or "on") != "off"
            for k in FEATURE_KEYS}


SITE_IMAGE_DEFAULTS = {
    "hero_1_img":  "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=1600&h=760&fit=crop&q=72",
    "hero_2_img":  "https://images.unsplash.com/photo-1571091718767-18b5b1457add?w=1600&h=760&fit=crop&q=72",
    "hero_3_img":  "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=1600&h=760&fit=crop&q=72",
    "hero_4_img":  "https://images.unsplash.com/photo-1572490122747-3968b75cc699?w=1600&h=760&fit=crop&q=72",
    "hero_5_img":  "https://images.unsplash.com/photo-1586190848861-99aa4a171e90?w=1600&h=760&fit=crop&q=72",
    "hero_6_img":  "https://images.unsplash.com/photo-1626645738196-c2a7c87a8f58?w=1600&h=760&fit=crop&q=72",
    "hero_7_img":  "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1600&h=760&fit=crop&q=72",
    "hero_8_img":  "https://images.unsplash.com/photo-1550547660-d9450f859349?w=1600&h=760&fit=crop&q=72",
    "hero_9_img":  "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=1600&h=760&fit=crop&q=72",
    "hero_10_img": "https://images.unsplash.com/photo-1568901839119-631418a3910d?w=1600&h=760&fit=crop&q=72",
    "catering_img":  "https://images.unsplash.com/photo-1550547660-d9450f859349?w=1600&h=760&fit=crop&q=70",
    "about_img":     "https://images.unsplash.com/photo-1552566626-52f8b828add9?w=900&h=1000&fit=crop&q=70",
    "franchise_img": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=1000&h=760&fit=crop&q=70",
    # Home — Instagram grid (8 tiles)
    "ig_1_img": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=400&h=400&fit=crop&q=70",
    "ig_2_img": "https://images.unsplash.com/photo-1571091718767-18b5b1457add?w=400&h=400&fit=crop&q=70",
    "ig_3_img": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=400&h=400&fit=crop&q=70",
    "ig_4_img": "https://images.unsplash.com/photo-1586190848861-99aa4a171e90?w=400&h=400&fit=crop&q=70",
    "ig_5_img": "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=400&h=400&fit=crop&q=70",
    "ig_6_img": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=400&h=400&fit=crop&q=70",
    "ig_7_img": "https://images.unsplash.com/photo-1572490122747-3968b75cc699?w=400&h=400&fit=crop&q=70",
    "ig_8_img": "https://images.unsplash.com/photo-1626645738196-c2a7c87a8f58?w=400&h=400&fit=crop&q=70",
    # Sub-page heroes that currently ship with a real photo
    "catering_hero_img": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=1600&h=760&fit=crop&q=72",
    "careers_hero_img":  "https://images.unsplash.com/photo-1552566626-52f8b828add9?w=1600&h=760&fit=crop&q=72",
    # Sign in / sign up / forgot-password panel backgrounds
    "login_img":    "https://images.unsplash.com/photo-1550547660-d9450f859349?w=800&h=1000&fit=crop&q=70",
    "register_img": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=800&h=1000&fit=crop&q=70",
    "forgot_img":   "https://images.unsplash.com/photo-1571091718767-18b5b1457add?w=800&h=1000&fit=crop&q=70",
    # Sub-page banners that currently render a styled placeholder (no default photo):
    #   about_hero_img, contact_hero_img, deals_hero_img,
    #   giftcards_hero_img, rewards_hero_img, faq_hero_img
}
