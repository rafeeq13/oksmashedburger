"""Check delivery + Uber for an order. Usage: python tools/check_delivery.py OK-4034"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order
from app.integrations import uber_gateway
from app.integrations.config import should_simulate


def main():
    num = sys.argv[1] if len(sys.argv) > 1 else "OK-4034"
    app = create_app()
    with app.app_context():
        o = Order.query.filter_by(number=num).first()
        if not o:
            print("NOT FOUND:", num)
            return 1
        print("=== %s ===" % num)
        print("status:", o.status, "| type:", o.order_type)
        print("created:", o.created_at)
        d = o.delivery
        if not d:
            print("DELIVERY: NONE")
        else:
            print("method:", d.method)
            print("status:", d.status)
            print("provider_ref:", d.provider_ref)
            print("tracking_url:", d.tracking_url)
            print("raw:", d.raw)
        print("uber enabled:", uber_gateway.is_enabled(o.store))
        print("uber simulate:", should_simulate(o.store, "uber_direct"))
        if d and d.provider_ref and uber_gateway.is_enabled(o.store):
            live = uber_gateway.get_delivery(o.store, d.provider_ref)
            print("uber live:", live)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
