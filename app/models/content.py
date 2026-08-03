"""Editable content lists.

Several parts of the site are *lists of small records* — hero slides, reviews,
job openings, news posts. They were literal `{% set … = [ … ] %}` blocks inside
the templates, so the client could change a heading from Page Content but not
the actual items. One generic row type plus a registry covers all of them
without a table per list.

`content_list(kind)` returns the admin's rows when there are any and the
built-in defaults otherwise, so a list is never empty on the live site just
because nobody has opened the admin yet. The admin page offers a one-click
import of those defaults, which is how the client takes over a list.
"""
from app.extensions import db
from .base import TimestampMixin

# field types the admin form knows how to render
TEXT, AREA, URL, NUM = "text", "textarea", "url", "number"


class ContentItem(TimestampMixin, db.Model):
    __tablename__ = "content_items"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), index=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    data = db.Column(db.JSON, default=dict, nullable=False)


# ── registry ────────────────────────────────────────────────────────────────
# kind, label, where it shows, the fields, and the content the site shipped with

CONTENT_LISTS = [
    {
        "kind": "hero_slides",
        "label": "Hero slides",
        "where": "Home page carousel",
        "fields": [("title", "Headline", TEXT), ("text", "Subtitle", AREA),
                   ("img", "Image URL", URL)],
        "defaults": [
            {"img": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=1600&h=760&fit=crop&q=72", "title": "Real smashed burgers, served fast.", "text": "Fresh-smashed, deal-forward, and tracked to your door. Delivery or pickup, you decide."},
            {"img": "https://images.unsplash.com/photo-1571091718767-18b5b1457add?w=1600&h=760&fit=crop&q=72", "title": "Double the smash, double the joy.", "text": "Two fresh-smashed patties, melty American cheese and our toasted bun."},
            {"img": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=1600&h=760&fit=crop&q=72", "title": "Loaded fries, zero regrets.", "text": "Crispy, cheesy and piled high, the perfect side to any smash."},
            {"img": "https://images.unsplash.com/photo-1572490122747-3968b75cc699?w=1600&h=760&fit=crop&q=72", "title": "Hand-spun shakes, thick and cold.", "text": "Vanilla, chocolate and more, blended fresh to order."},
            {"img": "https://images.unsplash.com/photo-1586190848861-99aa4a171e90?w=1600&h=760&fit=crop&q=72", "title": "Turn up the heat.", "text": "The Spicy Jalapeno Smash brings fresh jalapenos and a kick of heat."},
            {"img": "https://images.unsplash.com/photo-1626645738196-c2a7c87a8f58?w=1600&h=760&fit=crop&q=72", "title": "Crispy chicken, done right.", "text": "Golden, crunchy and stacked tall on a toasted brioche bun."},
            {"img": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1600&h=760&fit=crop&q=72", "title": "Plant-based and proud.", "text": "The Garden Vegan Smash, all the flavor with none of the beef."},
            {"img": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=1600&h=760&fit=crop&q=72", "title": "Delivery or pickup.", "text": "You choose how you want it, we smash it fresh either way."},
            {"img": "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=1600&h=760&fit=crop&q=72", "title": "From kitchen to doorstep.", "text": "Follow your order live, every step from the flat-top to your door."},
            {"img": "https://images.unsplash.com/photo-1568901839119-631418a3910d?w=1600&h=760&fit=crop&q=72", "title": "Deals that hit different.", "text": "Free delivery on your first order with code OKFREE."},
        ],
    },
    {
        "kind": "testimonials",
        "label": "Customer reviews",
        "where": "Home page “What locals have to say” and the About page",
        "fields": [("name", "Name", TEXT), ("when", "When", TEXT),
                   ("stars", "Stars (1-5)", NUM), ("text", "Review", AREA)],
        "defaults": [
            {"name": "Jessica Y.", "when": "2 weeks ago", "stars": 4, "text": "4 stars because the wait for food is not 5 star worthy! But the burgers themselves are absolutely worth coming back for."},
            {"name": "Jordan T.", "when": "1 month ago", "stars": 5, "text": "Dang delicious! Fresh, fast, great kid and gluten-free options. Both the outdoor and indoor seating areas are charming and great."},
            {"name": "Grainne N.", "when": "1 month ago", "stars": 5, "text": "The food here is SO GOOD. I cannot explain how perfectly balanced the flavours are, absolutely delicious! The shakes are unreal."},
            {"name": "Genevieve M.", "when": "2 months ago", "stars": 5, "text": "Amazing food. Had the smash and it was so juicy on a toasted bun. The fries were loaded and great to share."},
            {"name": "Marcus B.", "when": "3 months ago", "stars": 5, "text": "Best smashed burger in Philly, no contest. The crust on the patty is exactly right and the staff are lovely."},
        ],
    },
    {
        "kind": "jobs",
        "label": "Job openings",
        "where": "Join Our Team page",
        "fields": [("title", "Role", TEXT), ("type", "Hours", TEXT),
                   ("where", "Location", TEXT), ("desc", "Description", AREA)],
        "defaults": [
            {"title": "Grill Cook", "type": "Full time / Part time", "where": "All locations", "desc": "Smash, sear and plate on a busy flat-top. No experience needed, we train you."},
            {"title": "Shift Lead", "type": "Full time", "where": "Center City", "desc": "Run the floor during peak service, coach the crew and keep tickets moving."},
            {"title": "Cashier / Front of House", "type": "Part time", "where": "Fishtown", "desc": "Greet guests, take orders and keep the counter running fast and friendly."},
            {"title": "Delivery Driver", "type": "Flexible shifts", "where": "All locations", "desc": "Own-fleet delivery with guaranteed hourly pay plus tips. Valid license required."},
            {"title": "Kitchen Prep", "type": "Early shift", "where": "All locations", "desc": "Hand-form patties, prep sauces and set the kitchen up for a clean, fast service."},
            {"title": "Store Manager", "type": "Full time", "where": "New location", "desc": "Own a whole kitchen: your team, your numbers, your neighborhood."},
        ],
    },
    {
        "kind": "news",
        "label": "News posts",
        "where": "News page",
        "fields": [("title", "Headline", TEXT), ("date", "Date", TEXT),
                   ("tag", "Tag", TEXT), ("img", "Image URL", URL),
                   ("excerpt", "Excerpt", AREA)],
        "defaults": [
            {"title": "We are opening in Fishtown", "date": "12 July 2026", "tag": "Openings", "img": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=900&h=600&fit=crop&q=72", "excerpt": "Our second Philly kitchen is now serving on Frankford Ave, with the full menu, late weekend hours and our own delivery fleet."},
            {"title": "The Spicy Jalapeno Smash is back", "date": "28 June 2026", "tag": "Menu", "img": "https://images.unsplash.com/photo-1586190848861-99aa4a171e90?w=900&h=600&fit=crop&q=72", "excerpt": "Fresh jalapenos, pepper jack and our smoky sauce. Back on the menu by popular demand, and this time it is staying."},
            {"title": "Catering is now open for bookings", "date": "14 June 2026", "tag": "Catering", "img": "https://images.unsplash.com/photo-1571091718767-18b5b1457add?w=900&h=600&fit=crop&q=72", "excerpt": "Office lunches, parties and game days. Three packages, individually boxed, delivered hot and ready to serve."},
            {"title": "Live order tracking, from griddle to door", "date": "30 May 2026", "tag": "Product", "img": "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=900&h=600&fit=crop&q=72", "excerpt": "Follow every stage of your order in real time, with SMS and email updates at each step of the journey."},
            {"title": "Rewards: every bite now earns points", "date": "18 May 2026", "tag": "Rewards", "img": "https://images.unsplash.com/photo-1568901839119-631418a3910d?w=900&h=600&fit=crop&q=72", "excerpt": "Earn points on every order and redeem them against burgers, sides and shakes. No card needed, it is all in your account."},
            {"title": "How we make the OK sauce", "date": "02 May 2026", "tag": "Kitchen", "img": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=900&h=600&fit=crop&q=72", "excerpt": "Made fresh in every kitchen, every morning. Here is the story behind the sauce that started it all."}
        ],
    },
    {
        "kind": "faq",
        "label": "FAQ questions",
        "where": "FAQ / Help page",
        "fields": [("q", "Question", TEXT), ("a", "Answer", AREA),
                   ("group", "Section", TEXT)],
        "defaults": [
            {"q": "How do I track my order?", "a": "Once your order is confirmed, open the live tracker from your order confirmation email or the <a href=\"/tracking\" class=\"link-underline\">Track Order</a> page. You'll see each stage from kitchen to doorstep, plus your driver's live location for delivery.", "group": "Delivery"},
            {"q": "What areas do you deliver to?", "a": "We deliver within roughly 4 miles of each of our four Philadelphia stores. Enter your address or ZIP at checkout, or on the <a href=\"/locations\" class=\"link-underline\">Locations</a> page, and we'll confirm whether you're in a delivery zone and the estimated time.", "group": "Delivery"},
            {"q": "What payment methods do you accept?", "a": "We accept Visa, Mastercard and American Express, plus Apple Pay and Google Pay. You can also pay with OK gift cards and redeem OK Rewards points at checkout.", "group": "Payments"},
            {"q": "How do OK Rewards points work?", "a": "You earn 10 points for every $1 spent on qualifying orders. Points add up automatically when you're signed in, and you can redeem a free Classic Smash at 500 points. Members also get birthday treats, referral bonuses and members-only deals. <a href=\"/rewards\" class=\"link-underline\">See how rewards work</a>.", "group": "Rewards"},
            {"q": "How do I reset my password?", "a": "On the sign-in screen, tap \"Forgot password?\" and enter your email. We'll send a secure reset link that's valid for 30 minutes. If it doesn't arrive, check your spam folder or contact us and we'll help you back in.", "group": "Account"},
            {"q": "Do you have vegan and allergen info?", "a": "Yes. Every menu item lists its ingredients and common allergens, and vegan options are clearly labeled. Because our kitchens handle shared equipment, we can't guarantee an allergen-free environment, if you have a severe allergy, please let the store know before ordering.", "group": "Allergens"},
            {"q": "How do I use a promo code?", "a": "Add your items to the cart, then enter your code in the \"Promo code\" field at checkout and tap Apply. The discount updates your total instantly. Only one promo code can be used per order, and some codes have minimum spend or first-order conditions.", "group": "Payments"},
            {"q": "Can I schedule an order for later?", "a": "Absolutely. At checkout, choose \"Schedule for later\" and pick a date and time slot that works for you, up to 7 days ahead. We'll start smashing so it's fresh and ready right at your selected time.", "group": "Ordering"},
            {"q": "How do refunds work?", "a": "If something's wrong with your order, contact us within 48 hours and we'll make it right, usually a refund or a re-make. Approved refunds go back to your original payment method within 3–5 business days, or instantly as OK credit if you prefer.", "group": "Ordering"},
            {"q": "How do I redeem a gift card?", "a": "Enter your gift card number and PIN in the \"Gift card\" field at checkout, or add it to your account balance under Payment methods. The card value is applied to your order total, and any remaining balance stays on the card for next time.", "group": "Rewards"},
            {"q": "Can I order for a group or catering?", "a": "Yes, our Family Feast boxes and catering trays are built for groups. For large events, use the Catering option on our <a href=\"/contact\" class=\"link-underline\">Contact</a> page and our team will help you plan quantities, timing and delivery.", "group": "Ordering"},
            {"q": "How do I update my delivery address?", "a": "Sign in, open Account &rarr; Addresses, and add, edit or set a default address. You can also enter a new address at checkout for a one-off delivery without changing your saved defaults.", "group": "Account"},
            {"q": "Can I change or cancel my order after placing it?", "a": "You can edit or cancel within a short window before the kitchen starts your order, head to the live tracker and tap \"Modify order.\" Once we start smashing, we can't change it, but our support team is always happy to help sort out any issue.", "group": "Delivery"},
            {"q": "How do I delete my account or data?", "a": "You can request account deletion from Account &rarr; Privacy, or by contacting us. We'll remove your personal data in line with our privacy policy, keeping only what's legally required for completed transactions.", "group": "Account"}
        ],
    },
    {
        "kind": "catering_packages",
        "label": "Catering packages",
        "where": "Catering page",
        "fields": [("title", "Package", TEXT), ("price", "Price", TEXT),
                   ("serves", "Serves", TEXT),
                   ("popular", "Most popular? (yes / blank)", TEXT),
                   ("desc", "What's included, one per line", AREA)],
        "defaults": [
            {"title": "The Huddle", "serves": "Great for 10 to 15 people", "price": "$14 / person", "popular": "", "desc": "One smash burger per guest\nShared classic fries\nSauces, napkins and serveware"},
            {"title": "The Full Smash", "serves": "Great for 16 to 40 people", "price": "$18 / person", "popular": "yes", "desc": "Choice of two burgers per guest\nLoaded OK fries and classic fries\nVegan and gluten-friendly options\nSetup and serveware included"},
            {"title": "The Block Party", "serves": "Great for 40+ people", "price": "Custom quote", "popular": "", "desc": "Full menu build with your team\nOn-site setup and staffing options\nDedicated event contact\nInvoicing available"}
        ],
    },
]

LIST_BY_KIND = {c["kind"]: c for c in CONTENT_LISTS}


def spec(kind):
    return LIST_BY_KIND.get(kind)


def defaults_for(kind):
    c = spec(kind)
    return list(c["defaults"]) if c else []


def content_list(kind):
    """Admin rows if the client has taken this list over, defaults otherwise."""
    rows = (ContentItem.query
            .filter_by(kind=kind, is_active=True)
            .order_by(ContentItem.sort_order, ContentItem.id).all())
    if rows:
        return [dict(r.data or {}, _id=r.id) for r in rows]
    return defaults_for(kind)


def has_rows(kind):
    return ContentItem.query.filter_by(kind=kind).count() > 0


def import_defaults(kind):
    """Copy the built-in content into editable rows. Returns how many landed."""
    if has_rows(kind):
        return 0
    items = defaults_for(kind)
    for i, item in enumerate(items):
        db.session.add(ContentItem(kind=kind, sort_order=i, is_active=True, data=item))
    db.session.commit()
    return len(items)
