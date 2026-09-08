"""Complex local delivery order via real /cart/add — variants, addons, promo, tip.

    python tools/local_complex_order_test.py
"""
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from decimal import Decimal

from app import create_app
from app import cart as cartlib
from app.extensions import db
from app.integrations.square_gateway import build_square_order
from app.models.menu import Product, ProductAddon, ProductVariant
from app.models.order import Order, Payment
from app.models.site import SiteSetting
from app.models.store import Store, StoreHours
from app.models.user import User
from app.services.receipts import build_receipt_pdf


STORE_SLUG = "west-philadelphia"
PROMO = "STUDENT15"
TIP = 4.50


def csrf(client, path="/"):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else ""


def ensure_store_open(store):
    for h in StoreHours.query.filter_by(store_id=store.id).all():
        h.open_time = "00:00"
        h.close_time = "23:59"


def ensure_deals_on():
    row = SiteSetting.query.filter_by(key="feature_deals").first()
    if not row:
        db.session.add(SiteSetting(key="feature_deals", value="on"))
    else:
        row.value = "on"
    db.session.commit()


def ensure_smash_modifiers(smash):
    """Local DB may lack seed modifiers — add them for a realistic cart."""
    if not smash.variants:
        db.session.add_all([
            ProductVariant(product=smash, name="Single", price_delta=Decimal("-2.00")),
            ProductVariant(product=smash, name="Double", price_delta=Decimal("0"), is_default=True),
            ProductVariant(product=smash, name="Triple", price_delta=Decimal("3.00")),
        ])
    if not smash.addons:
        db.session.add_all([
            ProductAddon(product=smash, name="Add bacon", price=Decimal("1.50")),
            ProductAddon(product=smash, name="Extra patty", price=Decimal("2.50")),
            ProductAddon(product=smash, name="Avocado", price=Decimal("1.50")),
            ProductAddon(product=smash, name="Fried egg", price=Decimal("1.00")),
        ])
    db.session.commit()
    db.session.refresh(smash)


def add_to_cart(client, token, product, qty=1, variant_id=None, addon_qty=None, notes=""):
    data = {
        "_csrf": token,
        "product_slug": product.slug,
        "qty": str(qty),
        "next": "/cart",
    }
    if variant_id:
        data["variant_id"] = str(variant_id)
    for aid, n in (addon_qty or {}).items():
        data["addon_qty_%s" % aid] = str(n)
    if notes:
        data["notes"] = notes
    return client.post("/cart/add", data=data, follow_redirects=True)


def run():
    app = create_app()
    app.config["TESTING"] = True
    errors = []
    order = None

    with app.app_context():
        store = Store.query.filter_by(slug=STORE_SLUG, is_active=True).first()
        if not store:
            store = Store.query.filter_by(is_active=True).first()
        if not store:
            print("FAIL: no store")
            return 1

        ensure_store_open(store)
        ensure_deals_on()

        smash = Product.query.filter_by(slug="double-bacon-smash", is_active=True).first()
        loaded = Product.query.filter_by(slug="loaded-ok-fries", is_active=True).first()
        spicy = Product.query.filter_by(slug="spicy-jalapeno-smash", is_active=True).first()
        shake = Product.query.filter_by(slug="vanilla-shake", is_active=True).first()
        classic = Product.query.filter_by(slug="classic-fries", is_active=True).first()
        if not all([smash, loaded, spicy, shake, classic]):
            print("FAIL: seed products missing")
            return 1

        ensure_smash_modifiers(smash)
        triple = ProductVariant.query.filter_by(product_id=smash.id, name="Triple").first()
        addons = {a.name: a for a in ProductAddon.query.filter_by(product_id=smash.id).all()}

        client = app.test_client()
        with client.session_transaction() as sess:
            sess.clear()
            sess["store_slug"] = store.slug
            sess["order_type"] = "delivery"
            sess["promo"] = PROMO

        token = csrf(client, "/menu")

        cart_steps = [
            ("smash+mods", add_to_cart(
                client, token, smash, qty=2, variant_id=triple.id,
                addon_qty={
                    addons["Add bacon"].id: 1,
                    addons["Extra patty"].id: 1,
                    addons["Fried egg"].id: 1,
                },
                notes="Well done, extra sauce on the side",
            )),
            ("spicy", add_to_cart(client, token, spicy, notes="Mild heat only")),
            ("loaded fries", add_to_cart(client, token, loaded)),
            ("classic fries x2", add_to_cart(client, token, classic, qty=2)),
            ("shakes x2", add_to_cart(client, token, shake, qty=2, notes="Extra whipped cream on one")),
        ]
        for label, resp in cart_steps:
            if resp.status_code != 200:
                errors.append(("cart add %s" % label, "status %s" % resp.status_code))
            else:
                print("OK  cart add:", label)

        with client.session_transaction() as sess:
            cart = list(sess.get("cart") or [])

        with app.test_request_context():
            from flask import session
            session.update({"store_slug": store.slug, "order_type": "delivery", "promo": PROMO, "cart": cart})
            session.modified = True
            summary = cartlib.summary(
                store, tip=TIP, order_type="delivery",
                address_zip=store.zip_code,
                address_line1=store.address_line,
                address_city="Philadelphia",
                address_state="PA",
                address_lat=store.latitude,
                address_lng=store.longitude,
            )

        print("\n=== COMPLEX CART (%d lines) ===" % len(cart))
        print("Subtotal: $%.2f | Promo -$%.2f | Del $%.2f | Tax $%.2f | Tip $%.2f" % (
            summary["subtotal"], summary["promo"]["discount"],
            summary["delivery_fee"], summary["tax"], summary["tip"]))
        print("TOTAL: $%.2f" % summary["total"])
        for line in cart:
            opts = line.get("options") or {}
            bits = []
            if opts.get("variant"):
                bits.append(opts["variant"])
            if opts.get("addons"):
                bits.append("%d add-ons" % len(opts["addons"]))
            if opts.get("notes"):
                bits.append("note")
            print("  %dx %s @ $%s [%s]" % (
                line["qty"], line["name"], line["unit_price"], ", ".join(bits) or "plain"))

        smash_line = next((l for l in cart if l["product_id"] == smash.id), None)
        if not smash_line or not (smash_line.get("options") or {}).get("addons"):
            errors.append(("cart modifiers", "smash missing variant/addons in cart"))

        try:
            token = csrf(client, "/checkout")
            r = client.post(
                "/checkout",
                data={
                    "_csrf": token,
                    "order_type": "delivery",
                    "fulfillment": "asap",
                    "name": "Complex Test Guest",
                    "email": "complex-test@example.invalid",
                    "phone": "+12155550333",
                    "address_search": store.address_line,
                    "address_line1": store.address_line,
                    "address_line2": "Apt 4B",
                    "address_city": "Philadelphia",
                    "address_state": "PA",
                    "address_zip": store.zip_code,
                    "address_lat": str(store.latitude or ""),
                    "address_lng": str(store.longitude or ""),
                    "notes": "Complex local test — ring bell, leave at door",
                    "tip": "%.2f" % TIP,
                    "payment_method": "cash",
                },
                follow_redirects=True,
            )
            assert r.status_code == 200 and "order-confirmed" in (r.request.path or "")
            print("\nOK  checkout confirmed")
        except Exception as e:
            errors.append(("checkout", e))
            traceback.print_exc()

        order = Order.query.filter_by(customer_email="complex-test@example.invalid").order_by(Order.id.desc()).first()
        if order:
            try:
                assert len(order.items) == 5
                assert order.coupon_code == PROMO
                smash_item = next(i for i in order.items if i.product_id == smash.id)
                opts = smash_item.options or {}
                assert opts.get("variant") == "Triple"
                assert len(opts.get("addons") or []) >= 3
                assert float(order.tip) == TIP
                print("OK  order %s total $%s (%d items, smash has Triple + addons)" % (
                    order.number, order.total, len(order.items)))
            except Exception as e:
                errors.append(("order data", e))
                traceback.print_exc()

            try:
                body, _, _ = build_square_order(order, store)
                assert body.get("line_items") and not body.get("service_charges")
                mods = sum(len(li.get("modifiers") or []) for li in body["line_items"])
                print("OK  square payload: %d items, %d modifier lines" % (len(body["line_items"]), mods))
            except Exception as e:
                errors.append(("square", e))

            try:
                pdf = build_receipt_pdf(order)
                assert len(pdf) > 500
                print("OK  receipt PDF %d bytes" % len(pdf))
            except Exception as e:
                errors.append(("receipt", e))

            try:
                ac = app.test_client()
                with ac.session_transaction() as sess:
                    sess["user_id"] = User.query.filter(User.role.has(name="super_admin")).first().id
                r = ac.get("/admin/orders/%s" % order.number, follow_redirects=True)
                assert r.status_code == 200, "admin status %s" % r.status_code
                print("OK  admin order page")
            except Exception as e:
                errors.append(("admin", e))

    print("\n" + "=" * 50)
    if errors:
        print("FAILED %d:" % len(errors))
        for n, e in errors:
            print(" - %s: %s" % (n, e))
        return 1
    print("ALL PASSED — complex order %s" % (order.number if order else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
