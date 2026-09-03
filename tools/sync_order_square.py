import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.extensions import db
from app.models.order import Order, Payment
from app.services.order_sync import sync_order_integrations

num = sys.argv[1] if len(sys.argv) > 1 else "OK-4019"
app = create_app()
with app.app_context():
    o = Order.query.filter_by(number=num).first()
    if not o:
        print("not found", num)
        raise SystemExit(1)
    p = Payment.query.filter_by(order_id=o.id).first()
    r = sync_order_integrations(o, {"reference": p.provider_ref if p else None, "status": "succeeded"})
    db.session.refresh(o)
    print("order", o.number, o.store.slug)
    print("square", r.get("square"))
    print("square_order_id", o.square_order_id)
