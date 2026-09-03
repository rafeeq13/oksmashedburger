"""Sync Uber Direct delivery status for an order. Usage: python tools/sync_uber_delivery.py OK-4049"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order
from app.services.delivery import ensure_delivery_status_current


def main():
    num = sys.argv[1] if len(sys.argv) > 1 else ""
    if not num:
        print("Usage: python tools/sync_uber_delivery.py OK-4049")
        return 1
    app = create_app()
    with app.app_context():
        order = Order.query.filter_by(number=num).first()
        if not order:
            print("ORDER NOT FOUND:", num)
            return 1
        d = order.delivery
        print("before:", "order=", order.status, "| delivery=", d.status if d else None, "| ref=", d.provider_ref if d else None)
        ensure_delivery_status_current(order)
        d = order.delivery
        print("after:", "order=", order.status, "| delivery=", d.status if d else None, "| ref=", d.provider_ref if d else None)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
