"""Backfill Stripe PaymentIntent metadata for an order. Usage: python tools/backfill_stripe_order.py OK-4024"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order, Payment
from app.integrations.stripe_gateway import update_payment_intent
from app.services.order_details import stripe_payment_update


def main():
    num = sys.argv[1] if len(sys.argv) > 1 else "OK-4024"
    app = create_app()
    with app.app_context():
        o = Order.query.filter_by(number=num).first()
        if not o:
            print("not found", num)
            return 1
        p = Payment.query.filter_by(order_id=o.id).first()
        if not p or not p.provider_ref or str(p.provider_ref).startswith("demo_pi"):
            print("no real stripe payment for", num)
            return 1
        result = update_payment_intent(o.store, p.provider_ref, **stripe_payment_update(o))
        print("update:", result["status"])
        if result.get("raw"):
            print("raw:", result["raw"])
        return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
