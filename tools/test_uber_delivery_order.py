"""Place a Northeast delivery order and verify Uber Direct dispatch + processing."""
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
from app.integrations.config import active_integration_config, integration_env, should_simulate
from app.integrations.stripe_gateway import verify_payment_intent
from app.integrations import square_gateway, uber_gateway
from app.services.order_sync import sync_order_integrations
from app.services.orders import advance, set_status

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

        cfg = uber_gateway.store_uber_config(store)
        print("\n=== UBER DIRECT CONFIG ===")
        print("enabled:", uber_gateway.is_enabled(store))
        print("simulate:", should_simulate(store, "uber_direct"))
        print("env:", integration_env(store))
        print("customer_id:", cfg.get("customer_id") or "(empty)")
        print("client_id:", (cfg.get("client_id") or "")[:12] + "..." if cfg.get("client_id") else "(empty)")

        product = Product.query.filter_by(is_active=True).order_by(Product.id).first()
        if not product:
            print("ERROR: no products")
            return 1

        client = app.test_client()
        csrf(client)
        cart = [{
            "product_id": product.id,
            "slug": product.slug,
            "name": product.name,
            "image": product.image_url,
            "unit_price": float(product.base_price),
            "qty": 1,
            "options": {},
        }]

        with client.session_transaction() as sess:
            sess["store_slug"] = STORE_SLUG
            sess["cart"] = cart
            sess["order_type"] = "delivery"
            sess.pop("promo", None)

        tip = 3.00
        with app.test_request_context():
            from flask import session
            session["cart"] = cart
            session["order_type"] = "delivery"
            session.modified = True
            summary = cartlib.summary(store, tip=tip, order_type="delivery")
        total = summary["total"]

        print("\n=== CART ===")
        print("Items:", summary["count"], "| Subtotal: $%.2f | Delivery: $%.2f | TOTAL: $%.2f" % (
            summary["subtotal"], summary["delivery_fee"], total))

        sched = (datetime.now() + timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
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

        intent_id = pi_data.get("reference")
        if pi_data.get("client_secret"):
            intent_id, st = confirm_stripe_intent(store, pi_data["client_secret"])
            verified = verify_payment_intent(store, intent_id, total)
            if verified["status"] != "succeeded":
                print("ERROR: stripe verify", verified)
                return 1

        checkout_data = {
            "_csrf": token,
            "order_type": "delivery",
            "fulfillment": "scheduled",
            "scheduled_for": sched_str,
            "name": "Uber Direct Test",
            "email": "uber-test@example.invalid",
            "phone": "+12155550444",
            "address_search": "7200 Frankford Ave, Philadelphia, PA 19135",
            "address_line1": "7200 Frankford Ave",
            "address_line2": "Apt 3",
            "address_city": "Philadelphia",
            "address_state": "PA",
            "address_zip": "19135",
            "notes": "Uber Direct integration test",
            "tip": "%.2f" % tip,
            "payment_method": "card",
            "stripe_payment_intent": intent_id or "",
            "card_name": "Uber Direct Test",
        }

        resp = client.post("/checkout", data=checkout_data, follow_redirects=False)
        if resp.status_code not in (302, 303):
            print("ERROR: checkout", resp.status_code, resp.data[:400])
            return 1

        with client.session_transaction() as sess:
            oid = sess.get("last_order_id")
        order = Order.query.get(oid) if oid else Order.query.order_by(Order.id.desc()).first()
        db.session.refresh(order)
        payment = Payment.query.filter_by(order_id=order.id).first()

        print("\n=== ORDER ===")
        print("Number:", order.number, "| Status:", order.status, "| Payment:", order.payment_status)
        print("Type:", order.order_type, "| Total: $%s" % order.total)
        print("Address:", order.address_line1, order.address_city, order.address_zip)

        sync = sync_order_integrations(order, {"reference": payment.provider_ref if payment else intent_id, "status": "succeeded"})
        db.session.refresh(order)
        delivery = order.delivery
        uber = sync.get("delivery")
        print("\n=== UBER DIRECT ===")
        if delivery:
            print("method:", delivery.method, "| status:", delivery.status)
            print("provider_ref:", delivery.provider_ref)
            print("tracking_url:", delivery.tracking_url)
            if delivery.provider_ref and not should_simulate(store, "uber_direct"):
                live = uber_gateway.get_delivery(store, delivery.provider_ref)
                print("live status:", live.get("status"), "| id:", live.get("id"))
                if live.get("tracking_url"):
                    print("live tracking:", live.get("tracking_url"))
        else:
            print("NO delivery record")
        if uber:
            print("dispatch raw:", uber)

        print("\n=== PROCESS ORDER ===")
        for step in ("preparing", "ready", "out_for_delivery"):
            if order.status == "cancelled":
                break
            advance(order)
            db.session.refresh(order)
            print(" ->", order.status)
        if order.status not in ("cancelled", "completed") and order.order_type == "delivery":
            set_status(order, "completed")
            db.session.refresh(order)
            print(" ->", order.status)

        ok = bool(delivery and delivery.method == "uber_direct" and delivery.provider_ref)
        print("\nRESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
