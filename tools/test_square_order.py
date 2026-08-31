"""Place a test order locally and verify Square sync."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.order import Order, OrderItem, Payment
from app.models.store import Store
from app.models.menu import Product
from app.integrations import square_gateway
from app.integrations.config import active_integration_config, integration_env
from app.services.order_sync import sync_order_integrations


def main():
    app = create_app()
    with app.app_context():
        store = Store.query.filter_by(slug="south-snyder", is_active=True).first()
        if not store:
            store = Store.query.filter_by(is_active=True).first()
        if not store:
            print("ERROR: no active store")
            return 1

        cfg = active_integration_config(store, "square")
        print("Store:", store.slug)
        print("Square env:", integration_env(store))
        print("Square enabled:", square_gateway.is_enabled(store))
        print("Location ID:", cfg.get("location_id"))
        tok = (cfg.get("access_token") or "")
        print("Token:", (tok[:8] + "..." + tok[-4:]) if len(tok) > 12 else ("(empty)" if not tok else tok))

        product = Product.query.filter_by(is_active=True).first()
        if not product:
            print("ERROR: no product")
            return 1

        order = Order(
            store=store,
            order_type="pickup",
            customer_name="Square Test",
            customer_email="square-test@example.invalid",
            customer_phone="+12155550199",
            subtotal=Decimal("12.99"),
            tax=Decimal("1.04"),
            delivery_fee=Decimal("0"),
            tip=Decimal("2.00"),
            discount=Decimal("0"),
            total=Decimal("16.03"),
            payment_method="card",
            payment_status="paid",
            status="confirmed",
        )
        db.session.add(order)
        db.session.flush()
        order.number = "OK-%d" % (4000 + order.id)

        db.session.add(OrderItem(
            order=order,
            product_id=product.id,
            name=product.name,
            unit_price=Decimal("12.99"),
            qty=1,
            options={"variant": "Single", "addons": [{"name": "Extra Cheese", "price": 1.5, "qty": 1}]},
            line_total=Decimal("12.99"),
        ))
        db.session.add(Payment(
            order=order,
            provider="stripe",
            amount=order.total,
            status="succeeded",
            provider_ref="pi_test_square_local",
        ))
        db.session.commit()
        print("Created order:", order.number, "total=$%s" % order.total)

        payment_result = {"reference": "pi_test_square_local", "status": "succeeded"}
        results = sync_order_integrations(order, payment_result=payment_result)
        db.session.refresh(order)

        sq = results.get("square") or {}
        print("\n--- Square result ---")
        print("status:", sq.get("status"))
        print("reference:", sq.get("reference"))
        raw = sq.get("raw") or {}
        if raw.get("errors"):
            print("errors:", raw.get("errors"))
        elif raw.get("error"):
            print("error:", raw.get("error"))
        elif raw.get("demo"):
            print("simulated:", raw)
        else:
            order_obj = (raw.get("order") or {}).get("order") or {}
            print("square_state:", order_obj.get("state"))
            print("square_total:", order_obj.get("total_money"))
        print("order.square_order_id:", order.square_order_id)
        return 0 if sq.get("status") in ("synced", "simulated", "partial") else 2


if __name__ == "__main__":
    raise SystemExit(main())
