"""Place a delivery order and manually advance each admin stage."""
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
from app.services.order_sync import sync_order_integrations
from app.services.orders import advance

STORE_SLUG = "northeast-philadelphia"
ORDER_NUMBER = sys.argv[1] if len(sys.argv) > 1 else None


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


def place_order(store, product):
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

    sched = (datetime.now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    token = csrf(client, "/checkout")
    pi_resp = client.post(
        "/checkout/payment-intent",
        json={"amount": total},
        headers={"X-CSRF-Token": token},
    )
    pi_data = pi_resp.get_json() or {}
    if not pi_data.get("ok"):
        raise RuntimeError("payment-intent failed: %s" % pi_data)

    intent_id = pi_data.get("reference")
    if pi_data.get("client_secret"):
        intent_id, _ = confirm_stripe_intent(store, pi_data["client_secret"])
        verified = verify_payment_intent(store, intent_id, total)
        if verified["status"] != "succeeded":
            raise RuntimeError("stripe verify failed: %s" % verified)

    checkout_data = {
        "_csrf": token,
        "order_type": "delivery",
        "fulfillment": "scheduled",
        "scheduled_for": sched.strftime("%Y-%m-%dT%H:%M"),
        "name": "Manual Process Test",
        "email": "manual-test@example.invalid",
        "phone": "+12155550444",
        "address_search": "7200 Frankford Ave, Philadelphia, PA 19135",
        "address_line1": "7200 Frankford Ave",
        "address_line2": "Apt 5",
        "address_city": "Philadelphia",
        "address_state": "PA",
        "address_zip": "19135",
        "notes": "Manual admin processing test",
        "tip": "%.2f" % tip,
        "payment_method": "card",
        "stripe_payment_intent": intent_id or "",
        "card_name": "Manual Process Test",
    }
    resp = client.post("/checkout", data=checkout_data, follow_redirects=False)
    if resp.status_code not in (302, 303):
        raise RuntimeError("checkout failed: %s" % resp.status_code)

    with client.session_transaction() as sess:
        oid = sess.get("last_order_id")
    order = db.session.get(Order, oid)
    payment = Payment.query.filter_by(order_id=order.id).first()
    sync_order_integrations(
        order,
        {"reference": payment.provider_ref if payment else intent_id, "status": "succeeded"},
    )
    db.session.refresh(order)
    return order


def manual_advance(order):
    print("\n=== MANUAL PROCESS: %s (current: %s) ===" % (order.number, order.status))
    steps = []
    while order.status not in ("completed", "cancelled"):
        prev = order.status
        advance(order)
        db.session.refresh(order)
        steps.append("%s -> %s" % (prev, order.status))
        print("  advance:", steps[-1])
        if order.status == prev:
            break
    return steps


app = create_app()
with app.app_context():
    store = Store.query.filter_by(slug=STORE_SLUG, is_active=True).first()
    if not store:
        print("ERROR: store not found")
        raise SystemExit(1)

    if ORDER_NUMBER:
        order = Order.query.filter_by(number=ORDER_NUMBER).first()
        if not order:
            print("ERROR: order not found:", ORDER_NUMBER)
            raise SystemExit(1)
        print("Using existing order:", order.number, "| status:", order.status)
    else:
        product = Product.query.filter_by(is_active=True).order_by(Product.id).first()
        if not product:
            print("ERROR: no products")
            raise SystemExit(1)
        order = place_order(store, product)
        delivery = order.delivery
        print("\n=== PLACED ===")
        print("Number:", order.number, "| Status:", order.status, "| Total:", order.total)
        if delivery:
            print("Uber ref:", delivery.provider_ref)
            print("Tracking:", delivery.tracking_url)

    manual_advance(order)
    print("\nFINAL:", order.number, "|", order.status)
