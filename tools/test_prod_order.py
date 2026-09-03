"""Place a simple sandbox test order on production (Flask test client)."""
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app import cart as cartlib
from app.models.store import Store
from app.models.menu import Product
from app.models.order import Order, Payment
from app.integrations.config import active_integration_config
from app.integrations.stripe_gateway import verify_payment_intent
from app.integrations import square_gateway
from app.services.order_sync import sync_order_integrations

STORE_SLUG = "northeast-philadelphia"


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

        products = Product.query.filter_by(is_active=True).order_by(Product.id).limit(3).all()
        if len(products) < 1:
            print("ERROR: no active products")
            return 1

        client = app.test_client()
        csrf(client)

        cart = []
        for product in products[:2]:
            cart.append(
                {
                    "product_id": product.id,
                    "slug": product.slug,
                    "name": product.name,
                    "image": product.image_url,
                    "unit_price": float(product.base_price),
                    "qty": 1,
                    "options": {},
                }
            )

        with client.session_transaction() as sess:
            sess["store_slug"] = STORE_SLUG
            sess["cart"] = cart
            sess["order_type"] = "pickup"
            sess.pop("promo", None)

        tip = 2.00
        with app.test_request_context():
            from flask import session

            session["cart"] = cart
            session["order_type"] = "pickup"
            session.modified = True
            summary = cartlib.summary(store, tip=tip, order_type="pickup")
        total = summary["total"]

        print("\n=== CART SUMMARY ===")
        print("Store:", store.name)
        print("Items:", summary["count"], "| Subtotal: $%.2f" % summary["subtotal"])
        print("Tax: $%.2f | Tip: $%.2f | TOTAL: $%.2f" % (summary["tax"], summary["tip"], total))

        sched = (datetime.now() + timedelta(days=1)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
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
            "order_type": "pickup",
            "fulfillment": "scheduled",
            "scheduled_for": sched_str,
            "name": "Webhook Test Customer",
            "email": "webhook-test@example.invalid",
            "phone": "+12155550301",
            "notes": "Production webhook test order",
            "tip": "%.2f" % tip,
            "payment_method": "card",
            "stripe_payment_intent": intent_id or "",
            "card_name": "Webhook Test Customer",
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
        print("Total: $%s | Tip: $%s" % (order.total, order.tip))
        print("Stripe PI:", payment.provider_ref if payment else intent_id)

        sync = sync_order_integrations(
            order,
            {"reference": payment.provider_ref if payment else intent_id, "status": "succeeded"},
        )
        db.session.refresh(order)
        sq = sync.get("square") or {}
        print("\n=== SQUARE ===")
        print("Enabled:", square_gateway.is_enabled(store))
        print("Sync:", sq.get("status"), sq.get("reference"))
        if order.square_order_id:
            print("square_order_id:", order.square_order_id)

        ok = order.store_id == store.id and order.payment_status == "paid"
        print("\nRESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
