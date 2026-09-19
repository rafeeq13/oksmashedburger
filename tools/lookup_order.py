"""One-off: print order + payments by number fragment or id."""
import sys

from app import create_app
from app.models.order import Order, Payment

needle = (sys.argv[1] if len(sys.argv) > 1 else "4092").strip().upper().replace("OK-", "")

app = create_app()
with app.app_context():
    o = (
        Order.query.filter(Order.number.ilike(f"%{needle}%"))
        .order_by(Order.id.desc())
        .first()
    )
    if not o and needle.isdigit():
        o = Order.query.get(int(needle))
    if not o:
        print("NOT_FOUND", needle)
        raise SystemExit(1)
    print("id", o.id)
    print("number", o.order_number)
    print("status", o.status)
    print("payment_status", o.payment_status)
    print("total", o.total)
    print("payment_method", getattr(o, "payment_method", None))
    print("created_at", o.created_at)
    print("customer_email", o.customer_email)
    print("customer_name", o.customer_name)
    print("store_id", o.store_id)
    print("stripe_payment_intent", getattr(o, "stripe_payment_intent_id", None))
    for p in Payment.query.filter_by(order_id=o.id).order_by(Payment.id).all():
        print(
            "payment",
            p.id,
            p.provider,
            p.status,
            p.amount,
            p.transaction_id,
            p.created_at,
        )
