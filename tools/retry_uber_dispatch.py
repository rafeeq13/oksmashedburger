"""Retry Uber Direct dispatch for a failed delivery. Usage: python tools/retry_uber_dispatch.py OK-4034"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order
from app.services.delivery import retry_uber_dispatch


def main():
    num = sys.argv[1] if len(sys.argv) > 1 else "OK-4034"
    app = create_app()
    with app.app_context():
        order = Order.query.filter_by(number=num).first()
        if not order:
            print("NOT FOUND:", num)
            return 1
        print("Retrying Uber for", order.number, "| type:", order.order_type)
        delivery = retry_uber_dispatch(order)
        if not delivery:
            print("SKIP: not a delivery order or Uber not enabled")
            return 2
        print("method:", delivery.method)
        print("status:", delivery.status)
        print("provider_ref:", delivery.provider_ref)
        print("tracking_url:", delivery.tracking_url)
        if delivery.proof:
            print("error:", delivery.proof[:300])
        return 0 if delivery.provider_ref else 3


if __name__ == "__main__":
    raise SystemExit(main())
