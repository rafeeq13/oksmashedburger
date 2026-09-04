"""End-to-end integration test, Stripe, Square, Uber, SMTP per store.

Runs locally against the dev DB. Does not hit the HTTP checkout form; exercises
the same gateway + sync + notify pipeline used after checkout.

Usage:
  .venv\\Scripts\\python.exe tools/test_integrations_order.py
  .venv\\Scripts\\python.exe tools/test_integrations_order.py --store south-snyder
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.order import Order, OrderItem, Payment
from app.models.store import Store
from app.models.menu import Product
from app.integrations.config import integration_env, active_integration_config, should_simulate
from app.integrations import stripe_gateway, square_gateway
from app.integrations.smtp_gateway import is_enabled as smtp_enabled
from app.integrations.twilio_gateway import is_enabled as twilio_enabled
from app.integrations.uber_gateway import is_enabled as uber_enabled
from app.services.order_sync import sync_order_integrations
from app.services.order_details import payment_metadata


def _make_order(store, order_type="pickup"):
    product = Product.query.filter_by(is_active=True).first()
    if not product:
        raise RuntimeError("No active product in DB")

    subtotal = Decimal("14.99")
    tax = Decimal("1.20")
    tip = Decimal("2.00")
    delivery_fee = Decimal("3.99") if order_type == "delivery" else Decimal("0")
    total = subtotal + tax + tip + delivery_fee

    order = Order(
        store=store,
        order_type=order_type,
        customer_name="Integration Test",
        customer_email="integration-test@example.invalid",
        customer_phone="+12155550199",
        address="123 Test St, Philadelphia, PA 19147" if order_type == "delivery" else None,
        address_line1="123 Test St" if order_type == "delivery" else None,
        address_line2="Apt 1" if order_type == "delivery" else None,
        address_city="Philadelphia" if order_type == "delivery" else None,
        address_state="PA" if order_type == "delivery" else None,
        address_zip="19147" if order_type == "delivery" else None,
        subtotal=subtotal,
        tax=tax,
        delivery_fee=delivery_fee,
        tip=tip,
        discount=Decimal("0"),
        total=total,
        payment_method="card",
        payment_status="paid",
        status="confirmed",
    )
    db.session.add(order)
    db.session.flush()
    order.number = "OK-%d" % (5000 + order.id)
    db.session.add(OrderItem(
        order=order,
        product_id=product.id,
        name=product.name,
        unit_price=subtotal,
        qty=1,
        options={"variant": "Single"},
        line_total=subtotal,
    ))
    db.session.add(Payment(
        order=order,
        provider="stripe",
        amount=order.total,
        status="succeeded",
        provider_ref="pi_test_integration",
    ))
    db.session.commit()
    return order


def _stripe_test(store):
    mode = stripe_gateway.stripe_checkout_mode(store)
    sim = should_simulate(store, "stripe")
    created = stripe_gateway.create_payment_intent(store, 19.99, metadata={"test": "1"})
    ok = created["status"] in ("pending", "succeeded")
    note = ""
    if created["status"] == "pending" and created.get("client_secret"):
        note = "needs Elements confirm at checkout"
    elif (created.get("raw") or {}).get("demo"):
        note = "demo/simulated"
    elif created["status"] == "failed":
        note = (created.get("raw") or {}).get("error", "failed")
    return ok, mode, note or created["status"]


def _square_eval(store, sync_result, order):
    if not square_gateway.is_enabled(store):
        cfg = active_integration_config(store, "square")
        loc = (cfg.get("location_id") or "")
        if loc.startswith("sandbox-sq0idb") or loc.startswith("sq0idb-"):
            return False, "wrong location_id (Application ID | use L… Location ID)"
        if should_simulate(store, "square"):
            return True, "simulated (no token/location)"
        return False, "not configured"

    sq = sync_result.get("square") or {}
    status = sq.get("status")
    ok = status in ("synced", "simulated", "partial")
    detail = status or "skipped"
    raw = sq.get("raw") or {}
    if raw.get("errors"):
        detail = str(raw["errors"])
    elif raw.get("error"):
        detail = raw["error"]
    elif sq.get("reference"):
        detail = "%s ref=%s" % (status, str(sq["reference"])[:20])
    if order.square_order_id:
        detail += " square_order_id=%s" % order.square_order_id
    return ok, detail


def test_store(store, order_type="pickup"):
    print("\n" + "=" * 60)
    print("STORE:", store.name, "(%s)" % store.slug)
    print("integration_env:", integration_env(store))
    print("-" * 60)

    stripe_ok, stripe_mode, stripe_note = _stripe_test(store)
    print("[stripe]  mode=%-8s ok=%s  %s" % (stripe_mode, stripe_ok, stripe_note))

    sq_cfg = active_integration_config(store, "square")
    print("[square]  enabled=%s simulate=%s loc=%s" % (
        square_gateway.is_enabled(store),
        should_simulate(store, "square"),
        (sq_cfg.get("location_id") or "")[:24],
    ))

    print("[smtp]    enabled=%s simulate=%s host=%s" % (
        smtp_enabled(store), should_simulate(store, "smtp"),
        active_integration_config(store, "smtp").get("smtp_host", ""),
    ))
    print("[twilio]  enabled=%s simulate=%s" % (
        twilio_enabled(store), should_simulate(store, "twilio"),
    ))
    print("[uber]    enabled=%s simulate=%s" % (
        uber_enabled(store), should_simulate(store, "uber_direct"),
    ))

    order = _make_order(store, order_type=order_type)
    print("\nOrder:", order.number, order_type, "$%s" % order.total)

    payment_result = {"reference": "pi_test_integration", "status": "succeeded"}
    sync = sync_order_integrations(order, payment_result=payment_result)
    db.session.refresh(order)

    sq_ok, sq_detail = _square_eval(store, sync, order)
    print("[square sync]", sq_detail)

    delivery = sync.get("delivery")
    if order_type == "delivery" and delivery:
        print("[delivery]", getattr(delivery, "status", ""), getattr(delivery, "method", ""),
              getattr(delivery, "provider_ref", "") or "")

    # notifications (dry-run style | catch errors only)
    notify_ok = True
    notify_err = ""
    try:
        from app.services.notifications import notify_order_event
        notify_order_event(order, order.status)
    except Exception as exc:
        notify_ok = False
        notify_err = str(exc)
    print("[notify]  ok=%s %s" % (notify_ok, notify_err))

    overall = stripe_ok and (sq_ok or should_simulate(store, "square"))
    print("RESULT:", "PASS" if overall else "NEEDS ATTENTION")
    return overall


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", help="Test one store slug only")
    parser.add_argument("--type", choices=["pickup", "delivery"], default="pickup")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        q = Store.query.filter_by(is_active=True).order_by(Store.name)
        if args.store:
            q = q.filter_by(slug=args.store)
        stores = q.all()
        if not stores:
            print("No stores found")
            return 1

        passed = 0
        for store in stores:
            if test_store(store, order_type=args.type):
                passed += 1

        print("\n" + "=" * 60)
        print("SUMMARY: %d/%d stores passed" % (passed, len(stores)))
        return 0 if passed == len(stores) else 2


if __name__ == "__main__":
    raise SystemExit(main())
