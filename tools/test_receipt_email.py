"""Verify order email includes PDF receipt attachment."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order
from app.services.receipts import build_receipt_attachment, receipt_public_url
from app.services.notifications import notify_order_event


def main():
    number = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    app = create_app()
    with app.app_context():
        order = Order.query.filter_by(number=number).first() if number else Order.query.order_by(Order.id.desc()).first()
        if not order:
            print("ERROR: no order")
            return 1
        att = build_receipt_attachment(order)
        print("order:", order.number, "| event status:", order.status)
        print("pdf attachment:", "yes (%d bytes)" % len(att["content"]) if att else "NO")
        print("receipt url:", receipt_public_url(order) or "(none)")
        rows = notify_order_event(order, order.status if order.status in ("placed", "confirmed") else "confirmed")
        for r in rows:
            print("notify:", r.channel, r.status, r.event)
        return 0 if att else 2


if __name__ == "__main__":
    raise SystemExit(main())
