"""Debug Uber dispatch for an order. Usage: python tools/debug_uber_order.py OK-4034"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order
from app.integrations import uber_gateway


def main():
    num = sys.argv[1] if len(sys.argv) > 1 else "OK-4034"
    app = create_app()
    with app.app_context():
        o = Order.query.filter_by(number=num).first()
        if not o:
            print("NOT FOUND:", num)
            return 1
        print("=== %s ===" % num)
        print("phone:", o.customer_phone)
        print("address:", o.address_line1, o.address_city, o.address_state, o.address_zip)
        print("normalized phone:", uber_gateway._normalize_phone(o.customer_phone))
        print("dropoff json:", uber_gateway._dropoff_address(o))
        print("pickup json:", uber_gateway._pickup_address(o.store))
        d = o.delivery
        if d:
            print("existing delivery:", d.method, d.status, d.provider_ref)
        print("\n=== UBER create_delivery ===")
        res = uber_gateway.create_delivery(o.store, o)
        print(json.dumps(res, indent=2, default=str))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
