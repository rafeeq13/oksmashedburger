"""Check pickup order payment statuses."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order, Payment


def main():
    app = create_app()
    with app.app_context():
        print("=== RECENT PICKUP ORDERS ===")
        rows = Order.query.filter_by(order_type="pickup").order_by(Order.id.desc()).limit(20).all()
        for o in rows:
            p = Payment.query.filter_by(order_id=o.id).first()
            print(
                o.number,
                "| order:", o.status,
                "| payment:", o.payment_status,
                "| method:", o.payment_method,
                "| pi:", (p.provider_ref if p else None),
                "| pay_row:", (p.status if p else None),
                "| store:", o.store.slug if o.store else "?",
            )
        pending = Order.query.filter_by(order_type="pickup", payment_status="pending").count()
        paid = Order.query.filter_by(order_type="pickup", payment_status="paid").count()
        print("\npickup pending:", pending, "| paid:", paid)

        from datetime import datetime, timezone
        since = datetime(2025, 9, 1, tzinfo=timezone.utc)
        recent_pending = (
            Order.query.filter(
                Order.order_type == "pickup",
                Order.payment_status == "pending",
                Order.created_at >= since,
            )
            .order_by(Order.id.desc())
            .all()
        )
        print("\n=== PENDING PICKUP SINCE SEP 2025 ===", len(recent_pending))
        for o in recent_pending:
            print(o.number, o.store.slug, o.created_at, o.status)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
