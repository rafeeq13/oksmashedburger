#!/bin/bash
cd /var/www/oksmashedburger
set -a
source .env
set +a
.venv/bin/python - <<'PY'
from app import create_app
from app.models.order import Order, Payment

app = create_app()
with app.app_context():
    o = Order.query.filter_by(number="OK-4092").first()
    if not o:
        o = Order.query.get(92)  # OK-4092 => id 92 if formula 4000+id
    if not o:
        o = Order.query.filter(Order.number.like("%4092%")).first()
    if not o:
        print("NOT_FOUND")
    else:
        print("id", o.id)
        print("number", o.number)
        print("status", o.status)
        print("payment_status", o.payment_status)
        print("payment_method", o.payment_method)
        print("total", o.total)
        print("created_at", o.created_at)
        print("customer", o.customer_name, o.customer_email, o.customer_phone)
        print("store_id", o.store_id)
        print("square_order_id", o.square_order_id)
        for p in Payment.query.filter_by(order_id=o.id).all():
            print("payment_row", p.provider, p.status, p.amount, p.provider_ref)
PY
