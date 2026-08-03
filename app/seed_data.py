"""Idempotent seed: roles, an admin, a brand catalog, and TWO locations — each
with its own menu (own listing/prices/availability) and its own integrations."""
from decimal import Decimal

from .extensions import db
from .models import (
    Role, User, ROLES, Store, StoreHours, StoreDeliveryZone, StoreIntegration,
    Category, Product, StoreMenuItem, ProductVariant, ProductAddon,
    Order, OrderItem, Driver, Delivery, Coupon, GiftCard,
    Favorite, UserAddress, ContactMessage,
)

IMG = "https://images.unsplash.com/photo-{id}?w=800&h=600&fit=crop&q=70"
BURGER = [IMG.format(id=i) for i in ("1568901346375-23c9450c58cd", "1571091718767-18b5b1457add", "1550547660-d9450f859349", "1586190848861-99aa4a171e90", "1594212699903-ec8a3eca50f5")]
FRIES = [IMG.format(id=i) for i in ("1573080496219-bb080dd4f877", "1630384060421-cb20d0e0649d")]
SHAKE = [IMG.format(id=i) for i in ("1572490122747-3968b75cc699", "1568901839119-631418a3910d")]
CHICKEN = [IMG.format(id=i) for i in ("1626645738196-c2a7c87a8f58", "1562967914-608f82629710")]
SALAD = [IMG.format(id="1512621776951-a57141f2eefd")]

# category slug, name, icon, order, tile image, description
CATEGORIES = [
    ("burgers", "Burgers", "burger", 1, BURGER[0], "Fresh-smashed patties on toasted buns"),
    ("chicken", "Chicken", "drumstick-bite", 2, CHICKEN[0], "Crispy, juicy chicken done right"),
    ("sides", "Sides", "utensils", 3, FRIES[0], "Loaded fries and shareable extras"),
    ("shakes", "Shakes", "glass-water", 4, SHAKE[0], "Thick, hand-spun classic shakes"),
    ("vegan", "Vegan", "leaf", 5, SALAD[0], "Plant-based smashes and fresh greens"),
]

# slug, name, category, price, image, calories, allergens, tags, vegan, order, description
PRODUCTS = [
    ("the-ok-classic", "The OK Classic", "burgers", "8.49", BURGER[0], 620, ["gluten", "dairy"], ["popular"], False, 1,
     "Our signature single smash patty with melted American cheese, crisp lettuce, tomato, onion and house OK sauce on a toasted potato bun."),
    ("ok-classic-double", "The OK Classic Double", "burgers", "11.49", BURGER[1], 720, ["gluten", "dairy"], ["popular"], False, 2,
     "Two fresh-smashed patties layered with double American cheese, crisp lettuce, tomato and our signature OK sauce."),
    ("double-bacon-smash", "Double Bacon Smash", "burgers", "12.99", BURGER[2], 890, ["gluten", "dairy"], ["hot"], False, 3,
     "Double smash patties stacked with smoked bacon, melted cheddar, crispy fried onions and smoky BBQ sauce."),
    ("spicy-jalapeno-smash", "Spicy Jalapeño Smash", "burgers", "11.99", BURGER[3], 810, ["gluten", "dairy"], ["spicy"], False, 4,
     "Smash patty with pepper jack, fresh and pickled jalapeños, chipotle mayo and a kick of hot sauce for real heat."),
    ("mushroom-swiss-smash", "Mushroom Swiss Smash", "burgers", "12.49", BURGER[4], 780, ["gluten", "dairy"], [], False, 5,
     "Smash patty topped with sautéed garlic mushrooms, nutty melted Swiss and creamy roasted-garlic aioli."),
    ("buffalo-crisp-chicken", "Buffalo Crisp Chicken", "chicken", "10.99", CHICKEN[0], 700, ["gluten", "dairy"], ["spicy"], False, 1,
     "Buttermilk-fried chicken tossed in tangy buffalo sauce with cool ranch, lettuce and pickles on a toasted bun."),
    ("classic-crisp-chicken", "Classic Crisp Chicken", "chicken", "9.99", CHICKEN[1], 650, ["gluten"], [], False, 2,
     "Golden buttermilk-fried chicken breast with lettuce, tomato, pickles and mayo on a toasted bun."),
    ("loaded-ok-fries", "Loaded OK Fries", "sides", "6.99", FRIES[0], 540, ["dairy"], ["popular"], False, 1,
     "Crispy fries loaded with melty cheese sauce, smoky bacon bits, green onions and a drizzle of OK sauce."),
    ("classic-fries", "Classic Fries", "sides", "3.99", FRIES[1], 380, [], [], True, 2,
     "Golden, crispy skin-on fries, lightly salted. The perfect sidekick to any smash."),
    ("vanilla-shake", "Vanilla Shake", "shakes", "5.49", SHAKE[0], 520, ["dairy"], [], False, 1,
     "Thick, hand-spun vanilla shake made with real ice cream and finished with a swirl of whipped cream."),
    ("chocolate-shake", "Chocolate Shake", "shakes", "5.49", SHAKE[1], 560, ["dairy"], ["popular"], False, 2,
     "Rich chocolate shake blended thick with real ice cream and topped with whipped cream."),
    ("garden-vegan-smash", "Garden Vegan Smash", "vegan", "10.49", SALAD[0], 480, ["gluten"], ["veggie"], True, 1,
     "Plant-based smash patty with vegan cheese, lettuce, tomato, onion and vegan aioli on a toasted bun."),
]

# Real OK Smashed Burger locations. Each: name, address, zip, lat, lng, phone and
# opening hours. "hours" gives the Mon-Sun window; "fri_sat" (optional) overrides
# Friday & Saturday (e.g. later close). Close "00:00" = midnight, "01:00" = 1 AM
# (overnight) — Store.is_open_at handles both.
STORES = {
    "south-washington": {
        "name": "South Philadelphia (Washington Ave)",
        "address": "1801 Washington Ave, Unit D", "zip": "19146",
        "lat": 39.9377, "lng": -75.1745, "phone": "(267) 354-2901",
        "hours": ("08:00", "00:00"),
    },
    "north-philadelphia": {
        "name": "North Philadelphia",
        "address": "3533 North 5th Street", "zip": "19120",
        "lat": 40.0075, "lng": -75.1390, "phone": "(267) 360-2929",
        "hours": ("12:00", "00:00"),
    },
    "northeast-philadelphia": {
        "name": "Northeast Philadelphia",
        "address": "7074 Frankford Ave", "zip": "19135",
        "lat": 40.0252, "lng": -75.0490, "phone": "(215) 207-0040",
        "hours": ("12:00", "00:00"), "fri_sat": ("12:00", "01:00"),
    },
    "south-snyder": {
        "name": "South Philadelphia (Snyder Ave)",
        "address": "1426 Snyder Ave", "zip": "19145",
        "lat": 39.9229, "lng": -75.1687, "phone": "(215) 449-0767",
        "hours": ("12:00", "00:00"), "fri_sat": ("12:00", "01:00"),
    },
    "west-philadelphia": {
        "name": "West Philadelphia",
        "address": "2017 Lancaster Ave", "zip": "19104",
        "lat": 39.9660, "lng": -75.1830, "phone": "(215) 948-8965",
        "hours": ("16:00", "01:00"),
    },
}


def _hours(store, info):
    daily = info["hours"]
    fri_sat = info.get("fri_sat", daily)
    for d in range(7):                       # 0=Mon … 4=Fri, 5=Sat, 6=Sun
        o, c = fri_sat if d in (4, 5) else daily
        db.session.add(StoreHours(store=store, day_of_week=d, open_time=o, close_time=c))


def run_seed():
    if Store.query.first():
        print("[info] already seeded - skipping")
        return

    # Roles
    roles = {name: Role(name=name, description=name.replace("_", " ").title()) for name in ROLES}
    db.session.add_all(roles.values())
    db.session.flush()

    # Corporate admin
    admin = User(email="admin@oksmashedburger.com", first_name="OK", last_name="Admin",
                 role=roles["super_admin"], email_verified=True)
    admin.set_password("admin123")  # demo only — change on first login
    db.session.add(admin)

    # Categories + brand catalog
    cats = {}
    for slug, name, icon, order, image, desc in CATEGORIES:
        c = Category(slug=slug, name=name, icon=icon, sort_order=order, image_url=image, description=desc)
        cats[slug] = c
        db.session.add(c)
    db.session.flush()

    products = {}
    for slug, name, cat, price, img, cal, allerg, tags, vegan, order, desc in PRODUCTS:
        p = Product(slug=slug, name=name, category=cats[cat], base_price=Decimal(price),
                    image_url=img, calories=cal, allergens=allerg, tags=tags,
                    is_vegan=vegan, sort_order=order, description=desc)
        products[slug] = p
        db.session.add(p)
    db.session.flush()

    # A few variants / add-ons on the flagship product (used by the item page)
    dbl = products["ok-classic-double"]
    db.session.add_all([
        ProductVariant(product=dbl, name="Single", price_delta=Decimal("-2.00")),
        ProductVariant(product=dbl, name="Double", price_delta=Decimal("0.00"), is_default=True),
        ProductVariant(product=dbl, name="Triple", price_delta=Decimal("3.00")),
        ProductAddon(product=dbl, name="Add bacon", price=Decimal("1.50")),
        ProductAddon(product=dbl, name="Extra patty", price=Decimal("2.50")),
        ProductAddon(product=dbl, name="Avocado", price=Decimal("1.50")),
        ProductAddon(product=dbl, name="Fried egg", price=Decimal("1.00")),
    ])

    # Stores + per-store hours, delivery zones, integrations and MENUS
    stores = {}
    for slug, info in STORES.items():
        s = Store(slug=slug, name=info["name"], address_line=info["address"], zip_code=info["zip"],
                  latitude=info["lat"], longitude=info["lng"], phone=info["phone"],
                  email=f"{slug}@oksmashedburger.com")
        stores[slug] = s
        db.session.add(s)
        _hours(s, info)
        db.session.add_all([
            StoreDeliveryZone(store=s, name="Local Zone", radius_miles=1.5, delivery_fee=Decimal("9.99"),
                              min_order=Decimal("15.00"), est_minutes=20, color="#E0A200", zip_codes=[info["zip"]]),
            StoreDeliveryZone(store=s, name="Standard Zone", radius_miles=3.0, delivery_fee=Decimal("3.99"),
                              min_order=Decimal("20.00"), est_minutes=30, color="#3B82F6", zip_codes=[]),
            StoreDeliveryZone(store=s, name="Extended Zone", radius_miles=5.0, delivery_fee=Decimal("5.99"),
                              min_order=Decimal("25.00"), est_minutes=45, color="#22C55E", zip_codes=[]),
        ])
    db.session.flush()

    slugs = list(stores)
    primary = stores[slugs[0]]     # South Philadelphia (Washington Ave) — demo orders + staff
    secondary = stores[slugs[1]]   # North Philadelphia — the live own-fleet delivery demo

    # ── Every location owns its integrations (demo keys) ──────────────────
    # Each store gets Stripe (payments), Google Maps, and both notification
    # channels (Twilio SMS + SendGrid email) so checkout and order pings work.
    for slug, s in stores.items():
        tag = slug.replace("-", "_")
        db.session.add_all([
            StoreIntegration(store=s, provider="stripe", enabled=True,
                             config={"account_id": f"acct_{tag}", "publishable_key": f"pk_test_{tag}", "secret_key": f"sk_test_{tag}"}),
            StoreIntegration(store=s, provider="square", enabled=True,
                             config={"location_id": f"SQ_LOC_{tag}", "access_token": f"sq_{tag}_token"}),
            StoreIntegration(store=s, provider="google_maps", enabled=True, config={"api_key": "gmaps_shared"}),
            StoreIntegration(store=s, provider="twilio", enabled=True,
                             config={"account_sid": f"AC_{tag}", "auth_token": f"tok_{tag}", "from_number": "+12155550100"}),
            StoreIntegration(store=s, provider="sendgrid", enabled=True,
                             config={"api_key": f"SG.{tag}", "from_email": f"{slug}@oksmashedburger.com"}),
        ])

    # ── Every location carries the full menu; feature the two classics ────
    for s in stores.values():
        for p in products.values():
            db.session.add(StoreMenuItem(store=s, product=p,
                                         is_featured=p.slug in ("the-ok-classic", "double-bacon-smash")))

    # ── Store staff (for KDS / dashboards) ────────────────────────────────
    kitchen = User(email="kitchen@oksmashedburger.com", first_name="Kim", last_name="Cook",
                   role=roles["kitchen_staff"], store=primary, email_verified=True)
    kitchen.set_password("kitchen123")
    manager = User(email="manager@oksmashedburger.com", first_name="Morgan", last_name="Lee",
                   role=roles["store_manager"], store=primary, email_verified=True)
    manager.set_password("manager123")
    db.session.add_all([kitchen, manager])

    # ── A few live demo orders at the primary store (so KDS/tracking have data) ──
    demo = [
        ("preparing", "delivery", [("The OK Classic Double", "11.49", 1), ("Loaded OK Fries", "6.99", 1)]),
        ("confirmed", "pickup", [("Double Bacon Smash", "12.99", 2)]),
        ("placed", "delivery", [("Buffalo Crisp Chicken", "10.99", 1), ("Vanilla Shake", "5.49", 2)]),
    ]
    from app.services.notifications import notify_order_event
    for status, otype, items in demo:
        subtotal = sum(Decimal(p) * q for _, p, q in items)
        tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
        fee = Decimal("2.99") if otype == "delivery" else Decimal("0")
        order = Order(store=primary, status=status, order_type=otype, customer_name="Demo Guest",
                      customer_phone="(215) 555-0123", customer_email="demo@example.com",
                      subtotal=subtotal, tax=tax, delivery_fee=fee, total=subtotal + tax + fee,
                      payment_status="paid", payment_method="card")
        db.session.add(order)
        db.session.flush()
        order.number = f"OK-{4000 + order.id}"
        for name, price, qty in items:
            db.session.add(OrderItem(order=order, name=name, unit_price=Decimal(price), qty=qty,
                                     line_total=(Decimal(price) * qty), options={}))
        # Store has Twilio + SendGrid → notify by SMS and email.
        notify_order_event(order, order.status)

    # ── Own-fleet drivers + a driver login ────────────────────────────────
    driver_user = User(email="driver@oksmashedburger.com", first_name="Dev", last_name="Rider",
                       role=roles["driver"], store=secondary, email_verified=True)
    driver_user.set_password("driver123")
    db.session.add(driver_user)
    db.session.flush()
    sec_driver = Driver(name="Dev Rider", phone="(215) 555-0199", vehicle="Toyota Prius · ABC-1234", store=secondary, user=driver_user)
    pri_driver = Driver(name="Casey Wheels", phone="(215) 555-0177", vehicle="Honda Civic · XYZ-902", store=primary)
    db.session.add_all([sec_driver, pri_driver])
    db.session.flush()

    # A delivery already out for delivery at the secondary store, assigned to its
    # own driver (own-fleet dispatch).
    fitems = [("The OK Classic", "8.49", 1), ("Classic Fries", "3.99", 1)]
    fsub = sum(Decimal(p) * q for _, p, q in fitems)
    ftax = (fsub * Decimal("0.08")).quantize(Decimal("0.01"))
    ffee = Decimal("2.99")
    forder = Order(store=secondary, status="out_for_delivery", order_type="delivery",
                   customer_name="Alex Rivera", customer_phone="(215) 555-0143",
                   customer_email="alex.rivera@example.com",
                   address=f"{secondary.address_line}, Apt 2, {secondary.city} {secondary.zip_code}",
                   subtotal=fsub, tax=ftax, delivery_fee=ffee, total=fsub + ftax + ffee,
                   payment_status="paid", payment_method="card")
    db.session.add(forder)
    db.session.flush()
    forder.number = f"OK-{4000 + forder.id}"
    for name, price, qty in fitems:
        db.session.add(OrderItem(order=forder, name=name, unit_price=Decimal(price), qty=qty,
                                 line_total=(Decimal(price) * qty), options={}))
    db.session.add(Delivery(order=forder, method="own", status="assigned", driver=sec_driver, fee=ffee))
    notify_order_event(forder, forder.status)

    # ── Brand-wide promo codes + a demo gift card ─────────────────────────
    db.session.add_all([
        Coupon(code="OKFIRST", kind="free_delivery", value=0, min_order=Decimal("0"),
               requires_code=False, description="Free delivery on your order", active=True),
        Coupon(code="SAVE5", kind="fixed", value=Decimal("5"), min_order=Decimal("20"),
               requires_code=True, description="$5 off orders over $20", active=True),
        Coupon(code="STUDENT15", kind="percent", value=Decimal("15"), min_order=Decimal("0"),
               requires_code=False, description="15% off for students", active=True),
        GiftCard(code="OKGC-GIFT25", initial_balance=Decimal("25"), balance=Decimal("25"),
                 active=True, sender_name="OK Smashed Burger", message="Enjoy a treat on us!"),
    ])

    # ── A demo customer with loyalty points (rewards + points redemption) ──
    guest = User(email="guest@oksmashedburger.com", first_name="Jordan", last_name="Miller",
                 role=roles["customer"], email_verified=True, loyalty_points=1240,
                 phone="(215) 555-0100")
    guest.set_password("guest123")
    db.session.add(guest)
    db.session.flush()

    # Give the demo customer some favorites, a saved address and a message.
    for slug in ("the-ok-classic", "double-bacon-smash", "loaded-ok-fries", "chocolate-shake"):
        db.session.add(Favorite(user_id=guest.id, product_id=products[slug].id))
    db.session.add_all([
        UserAddress(user_id=guest.id, label="Home", recipient="Jordan Miller",
                    line1="1420 Pine Street", line2="Apt 3B", city="Philadelphia",
                    state="PA", zip_code="19102", phone="(215) 555-0100", is_default=True),
        UserAddress(user_id=guest.id, label="Work", recipient="Jordan Miller",
                    line1="1801 Market Street", line2="Floor 12", city="Philadelphia",
                    state="PA", zip_code="19103", phone="(215) 555-0188"),
        ContactMessage(name="Priya Shah", email="priya@example.com", subject="Catering",
                       message="Do you cater office lunches for ~30 people in Center City?"),
    ])

    db.session.commit()
    print(f"[ok] seeded: {len(stores)} stores (own menu + integrations); staff kitchen@/manager@ (pw *123); "
          "driver driver@ (driver123); customer guest@ (guest123, 1240 pts); "
          "coupons OKFIRST/SAVE5/STUDENT15 + gift card OKGC-GIFT25 ($25); "
          "demo orders + 1 live own-fleet delivery; admin admin@oksmashedburger.com / admin123")
