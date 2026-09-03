"""Test order cancellation wiring (Stripe refund + Square cancel + notify)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.order import Order
from app.services.order_cancel import cancel_order


def main():
    number = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not number:
        print("Usage: python tools/test_order_cancel.py OK-4026")
        return 1

    app = create_app()
    with app.app_context():
        order = Order.query.filter_by(number=number).first()
        if not order:
            print("ERROR: order not found:", number)
            return 1

        print("=== BEFORE ===")
        print("status:", order.status, "| payment:", order.payment_status)
        print("stripe:", order.payment.provider_ref if order.payment else None)
        print("square:", order.square_order_id)

        order, results = cancel_order(order)
        db.session.refresh(order)

        print("\n=== CANCEL RESULTS ===")
        for provider, res in results.items():
            print(provider, ":", res)

        print("\n=== AFTER ===")
        print("status:", order.status, "| payment:", order.payment_status)
        if order.payment:
            print("payment record:", order.payment.status, order.payment.provider_ref)

        ok = order.status == "cancelled"
        print("\nRESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
