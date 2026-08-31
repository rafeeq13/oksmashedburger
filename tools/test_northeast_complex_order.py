"""Place a complex sandbox delivery order for Northeast Philadelphia.

Tests: multi-item cart + addons, STUDENT15 % deal, tip, delivery, location Stripe.
"""
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app import cart as cartlib
from app.models.store import Store
from app.models.menu import Product, ProductAddon
from app.models.order import Order, Payment
from app.models.site import SiteSetting
from app.integrations.config import active_integration_config
from app.integrations.stripe_gateway import create_payment_intent, verify_payment_intent
from app.integrations import square_gateway
from app.services.order_sync import sync_order_integrations


STORE_SLUG = "northeast-philadelphia"
PROMO_CODE = "STUDENT15"


def csrf(client, path="/"):
    html = client.get(path).data.decode("utf-8", "replace")
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else ""


def confirm_stripe_intent(store, client_secret):
    import stripe
    cfg = active_integration_config(store, "stripe")
    stripe.api_key = cfg["secret_key"]
    intent = stripe.PaymentIntent.confirm(
        client_secret.split("_secret_")[0],
        payment_method="pm_card_visa",
    )
    return intent.id, intent.status


def main():
    app = create_app()
    with app.app_context():
        store = Store.query.filter_by(slug=STORE_SLUG, is_active=True).first()
        if not store:
            print("ERROR: store not found")
            return 1

        deals_row = SiteSetting.query.filter_by(key="feature_deals").first()
        if not deals_row:
            deals_row = SiteSetting(key="feature_deals", value="on")
            db.session.add(deals_row)
        elif deals_row.value != "on":
            deals_row.value = "on"
        db.session.commit()

        burger = Product.query.filter_by(slug="muhammad-rafeeq", is_active=True).first()
        fries = Product.query.filter_by(slug="loaded-ok-fries", is_active=True).first()
        smash = Product.query.filter_by(slug="double-bacon-smash", is_active=True).first()
        shake = Product.query.filter_by(slug="vanilla-shake", is_active=True).first()
        if not all([burger, fries, smash, shake]):
            print("ERROR: missing products")
            return 1

        addons = {a.name: a for a in ProductAddon.query.filter_by(product_id=burger.id).all()}
        bacon = addons.get("Add bacon")
        avocado = addons.get("Avocado")
        patty = addons.get("Extra patty")
        egg = addons.get("Fried egg")

        client = app.test_client()
        token = csrf(client)

        with client.session_transaction() as sess:
            sess["store_slug"] = STORE_SLUG
            sess.pop("promo", None)

        # Complex cart built directly (same shape as cartlib.add_item)
        def line(product, qty=1, addon_ids=None, notes=""):
            unit = float(product.base_price)
            options = {}
            addons = []
            for aid in addon_ids or []:
                a = ProductAddon.query.get(aid)
                if a and a.product_id == product.id:
                    unit += float(a.price)
                    addons.append({"name": a.name, "price": float(a.price), "qty": 1})
            if addons:
                options["addons"] = addons
            if notes:
                options["notes"] = notes
            return {
                "product_id": product.id,
                "slug": product.slug,
                "name": product.name,
                "image": product.image_url,
                "unit_price": round(unit, 2),
                "qty": qty,
                "options": options,
            }

        addon_ids = [a.id for a in [bacon, avocado, patty, egg] if a]
        cart = [
            line(burger, 1, addon_ids, "Extra crispy, no onions"),
            line(smash, 2),
            line(fries, 1),
            line(shake, 1, notes="Extra whipped cream"),
        ]
        with client.session_transaction() as sess:
            sess["cart"] = cart
            sess["order_type"] = "delivery"
            sess["promo"] = PROMO_CODE

        tip = 4.50
        with app.test_request_context():
            from flask import session
            session["cart"] = cart
            session["promo"] = PROMO_CODE
            session["order_type"] = "delivery"
            session.modified = True
            summary = cartlib.summary(store, tip=tip, order_type="delivery")
        total = summary["total"]
        print("\n=== CART SUMMARY ===")
        print("Store:", store.name)
        print("Items:", summary["count"], "| Subtotal: $%.2f" % summary["subtotal"])
        print("Promo:", summary["promo"]["code"], "-$%.2f" % summary["promo"]["discount"])
        print("Delivery: $%.2f | Tax: $%.2f | Tip: $%.2f" % (
            summary["delivery_fee"], summary["tax"], summary["tip"]))
        print("TOTAL: $%.2f" % total)

        # Scheduled — store may be closed for ASAP on Mondays
        sched = (datetime.now() + timedelta(days=1)).replace(hour=13, minute=30, second=0, microsecond=0)
        sched_str = sched.strftime("%Y-%m-%dT%H:%M")

        token = csrf(client, "/checkout")
        pi_resp = client.post(
            "/checkout/payment-intent",
            json={"amount": total},
            headers={"X-CSRF-Token": token},
        )
        pi_data = pi_resp.get_json() or {}
        if not pi_data.get("ok"):
            print("ERROR: payment-intent", pi_resp.status_code, pi_data)
            return 1

        stripe_cfg = active_integration_config(store, "stripe")
        print("\n=== STRIPE ===")
        print("Account:", stripe_cfg.get("account_id"))
        print("Mode:", pi_data.get("mode"), "| Demo:", pi_data.get("demo"))

        intent_id = pi_data.get("reference")
        if pi_data.get("client_secret"):
            intent_id, st = confirm_stripe_intent(store, pi_data["client_secret"])
            print("Confirmed PaymentIntent:", intent_id, st)
            verified = verify_payment_intent(store, intent_id, total)
            print("Verified:", verified["status"], verified.get("reference"))
            if verified["status"] != "succeeded":
                print("ERROR: payment verification failed", verified)
                return 1

        checkout_data = {
            "_csrf": token,
            "order_type": "delivery",
            "fulfillment": "scheduled",
            "scheduled_for": sched_str,
            "name": "Northeast Sandbox Test",
            "email": "northeast-test@example.invalid",
            "phone": "+12155550200",
            "address_search": "7014 Frankford Ave, Philadelphia, PA 19135",
            "address_line1": "7014 Frankford Ave",
            "address_line2": "Unit 2",
            "address_city": "Philadelphia",
            "address_state": "PA",
            "address_zip": "19135",
            "notes": "Ring doorbell — complex sandbox test order",
            "tip": "%.2f" % tip,
            "payment_method": "card",
            "stripe_payment_intent": intent_id or "",
            "card_name": "Northeast Sandbox Test",
        }

        resp = client.post("/checkout", data=checkout_data, follow_redirects=False)
        if resp.status_code not in (302, 303):
            print("ERROR: checkout status", resp.status_code, resp.data[:500])
            return 1

        with client.session_transaction() as sess:
            oid = sess.get("last_order_id")
        order = Order.query.get(oid) if oid else Order.query.order_by(Order.id.desc()).first()
        if not order:
            print("ERROR: no order created")
            return 1

        db.session.refresh(order)
        payment = Payment.query.filter_by(order_id=order.id).first()

        print("\n=== ORDER PLACED ===")
        print("Number:", order.number)
        print("Status:", order.status, "| Payment:", order.payment_status)
        print("Type:", order.order_type, "| Scheduled:", order.scheduled_for)
        print("Coupon:", order.coupon_code, "| Discount: $%s" % order.discount)
        print("Subtotal: $%s | Tax: $%s | Delivery: $%s | Tip: $%s | Total: $%s" % (
            order.subtotal, order.tax, order.delivery_fee, order.tip, order.total))
        print("Items:", len(order.items))
        for it in order.items:
            opts = it.options or {}
            addons = opts.get("addons") or []
            extra = (" + %d add-ons" % len(addons)) if addons else ""
            note = (' note="%s"' % opts["notes"]) if opts.get("notes") else ""
            print("  - %dx %s @ $%s%s%s" % (it.qty, it.name, it.unit_price, extra, note))

        print("\n=== STRIPE PAYMENT ===")
        print("Provider ref:", payment.provider_ref if payment else None)
        print("Stripe account:", stripe_cfg.get("account_id"))

        sync = sync_order_integrations(order, {"reference": payment.provider_ref if payment else intent_id,
                                               "status": "succeeded"})
        db.session.refresh(order)
        sq = sync.get("square") or {}
        print("\n=== SQUARE ===")
        print("Enabled:", square_gateway.is_enabled(store))
        print("Sync:", sq.get("status"), sq.get("reference"))
        if order.square_order_id:
            print("square_order_id:", order.square_order_id)

        delivery = sync.get("delivery")
        if delivery:
            print("\n=== DELIVERY ===")
            print("Method:", delivery.method, "| Status:", delivery.status)

        ok = (
            order.store_id == store.id
            and order.order_type == "delivery"
            and float(order.tip) == tip
            and order.coupon_code == PROMO_CODE
            and order.payment_status == "paid"
            and len(order.items) >= 4
        )
        print("\nRESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
