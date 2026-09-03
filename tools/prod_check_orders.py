from app import create_app
from app.models.order import Order, Payment
from app.models.store import Store
from app.integrations.config import active_integration_config, integration_env, should_simulate
from app.integrations import square_gateway, stripe_gateway

app = create_app()
with app.app_context():
    print("=== LAST 10 ORDERS ===")
    for o in Order.query.order_by(Order.id.desc()).limit(10):
        p = Payment.query.filter_by(order_id=o.id).first()
        ref = p.provider_ref if p else None
        demo = bool((p.raw or {}).get("demo")) if p and p.raw else False
        print(
            o.number,
            o.store.slug if o.store else "?",
            o.payment_status,
            "stripe=", ref,
            "demo=", demo,
            "square=", o.square_order_id or "NONE",
            o.created_at,
        )

    print("\n=== STORE INTEGRATIONS ===")
    for s in Store.query.filter_by(is_active=True).order_by(Store.name):
        st = active_integration_config(s, "stripe")
        sq = active_integration_config(s, "square")
        sk = (st.get("secret_key") or "")
        loc = (sq.get("location_id") or "")
        print("---", s.slug, "| env:", integration_env(s))
        print(
            "  stripe: connected=", stripe_gateway.is_connected(s),
            "simulate=", should_simulate(s, "stripe"),
            "acct=", st.get("account_id"),
            "sk_prefix=", sk[:12] if sk else "(empty)",
        )
        print(
            "  square: enabled=", square_gateway.is_enabled(s),
            "simulate=", should_simulate(s, "square"),
            "loc=", loc[:35],
        )

    o = Order.query.filter_by(number="OK-4019").first()
    if o:
        p = Payment.query.filter_by(order_id=o.id).first()
        print("\n=== OK-4019 DETAIL ===")
        print("store:", o.store.slug, o.store.name)
        print("total:", o.total, "paid:", o.payment_status)
        print("payment ref:", p.provider_ref if p else None)
        print("payment status:", p.status if p else None)
        print("payment raw:", p.raw if p else None)
        print("square_order_id:", o.square_order_id)

        if p and p.provider_ref and not str(p.provider_ref).startswith("demo_pi"):
            import stripe
            cfg = active_integration_config(o.store, "stripe")
            stripe.api_key = cfg.get("secret_key")
            try:
                pi = stripe.PaymentIntent.retrieve(p.provider_ref)
                print("stripe API verify:", pi.status, "$" + str(pi.amount / 100), "acct", cfg.get("account_id"))
            except Exception as exc:
                print("stripe API verify FAILED:", exc)
