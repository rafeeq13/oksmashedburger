"""Check one order in DB + Stripe + Square. Usage: python tools/check_order.py OK-4024"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.order import Order, Payment
from app.integrations.config import active_integration_config
from app.integrations import square_gateway


def main():
    num = sys.argv[1] if len(sys.argv) > 1 else "OK-4024"
    app = create_app()
    with app.app_context():
        o = Order.query.filter_by(number=num).first()
        if not o:
            print("ORDER: NOT FOUND", num)
            return 1
        p = Payment.query.filter_by(order_id=o.id).first()
        print("=== %s DB ===" % num)
        print("store:", o.store.slug, "|", o.store.name)
        print("type:", o.order_type, "| status:", o.status, "| payment:", o.payment_status)
        print("customer:", o.customer_name, "|", o.customer_email, "|", o.customer_phone)
        print("address:", o.address or "(pickup)")
        print(
            "charges: subtotal=%s tax=%s delivery=%s tip=%s discount=%s total=%s"
            % (o.subtotal, o.tax, o.delivery_fee, o.tip, o.discount, o.total)
        )
        print("coupon:", o.coupon_code, "| notes:", (o.notes or "")[:80])
        for it in o.items:
            print("  item:", it.qty, "x", it.name, "@", it.unit_price, "=", it.line_total)
        print("stripe_ref:", p.provider_ref if p else None)
        print("stripe_status:", p.status if p else None)
        print("payment_raw:", p.raw if p else None)
        print("square_order_id:", o.square_order_id or "NONE")
        print("created:", o.created_at)

        ref = p.provider_ref if p else None
        if ref and not str(ref).startswith("demo_pi"):
            import stripe

            cfg = active_integration_config(o.store, "stripe")
            stripe.api_key = cfg.get("secret_key")
            print("stripe_account_config:", cfg.get("account_id"))
            try:
                acct = stripe.Account.retrieve()
                print("stripe_api_account:", acct.id)
            except Exception as exc:
                print("stripe_account_lookup:", exc)
            try:
                pi = stripe.PaymentIntent.retrieve(ref)
                print("\n=== STRIPE API ===")
                print("pi:", pi.id)
                print("status:", pi.status)
                print("amount:", "$%.2f" % (pi.amount / 100))
                print("description:", pi.description)
                print("receipt_email:", getattr(pi, "receipt_email", None))
                meta = dict(pi.metadata or {})
                for k in sorted(meta.keys()):
                    print("  meta.%s:" % k, meta[k])
                ship = getattr(pi, "shipping", None)
                if ship:
                    addr = ship.get("address") if hasattr(ship, "get") else getattr(ship, "address", None)
                    print("shipping_name:", ship.get("name") if hasattr(ship, "get") else getattr(ship, "name", None))
                    print("shipping_address:", addr)
            except Exception as exc:
                print("STRIPE ERROR:", exc)
        else:
            print("\n=== STRIPE ===", "demo or no ref")

        sq_id = o.square_order_id
        if sq_id and not str(sq_id).startswith("sq_demo"):
            from app.integrations.square_gateway import _request

            r = _request(o.store, "GET", "/v2/orders/%s" % sq_id)
            print("\n=== SQUARE API ===")
            if r.get("errors"):
                print("errors:", r["errors"])
            else:
                so = r.get("order") or {}
                print("square_id:", so.get("id"))
                print("state:", so.get("state"))
                print("reference_id:", so.get("reference_id"))
                print("total:", so.get("total_money"))
                print("metadata:", so.get("metadata"))
                for li in (so.get("line_items") or [])[:10]:
                    print("  line:", li.get("quantity"), li.get("name"), li.get("base_price_money"))
                for sc in so.get("service_charges") or []:
                    print("  charge:", sc.get("name"), sc.get("amount_money"))
        elif square_gateway.is_enabled(o.store):
            print("\n=== SQUARE ===", "enabled but square_order_id=", sq_id or "NONE")
        else:
            print("\n=== SQUARE ===", "not enabled/simulated")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
