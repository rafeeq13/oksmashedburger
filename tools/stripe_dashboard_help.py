import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.models.order import Order, Payment
from app.integrations.config import active_integration_config


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "northeast-philadelphia"
    app = create_app()
    with app.app_context():
        store = Store.query.filter_by(slug=slug).first()
        cfg = active_integration_config(store, "stripe")
        sk = (cfg.get("secret_key") or "").strip()
        pk = (cfg.get("publishable_key") or "").strip()

        print("STORE:", store.name)
        print("stripe_account_id (admin):", cfg.get("account_id"))
        print("publishable_key:", pk)
        print("secret_key_prefix:", sk[:20] + "..." if sk else "(empty)")

        if not sk or sk.startswith("sk_test_south") or "northeast_philadelphia" in sk:
            print("\nWARN: looks like fake/seed key - no real Stripe dashboard")
            return 1

        import stripe
        stripe.api_key = sk

        acct = stripe.Account.retrieve()
        print("\n--- STRIPE ACCOUNT (from API key) ---")
        print("id:", acct.id)
        print("email:", getattr(acct, "email", None) or "(not set)")
        print("country:", getattr(acct, "country", None))
        bp = getattr(acct, "business_profile", None) or {}
        if bp:
            print("business_name:", bp.get("name") if isinstance(bp, dict) else getattr(bp, "name", None))
        print("charges_enabled:", getattr(acct, "charges_enabled", None))

        print("\n--- LAST 8 PAYMENT INTENTS (search these in dashboard) ---")
        pis = stripe.PaymentIntent.list(limit=8)
        for pi in pis.data:
            meta = dict(pi.metadata or {})
            print(pi.id, "|", pi.status, "|", "$%.2f" % (pi.amount / 100), "|", meta.get("order_number", ""))

        print("\n--- ORDERS IN OUR DB (this store) ---")
        for o in Order.query.filter_by(store_id=store.id).order_by(Order.id.desc()).limit(5):
            p = Payment.query.filter_by(order_id=o.id).first()
            ref = p.provider_ref if p else None
            demo = "DEMO" if ref and str(ref).startswith("demo_pi") else "REAL"
            print(o.number, demo, ref)

        print("\n--- HOW TO FIND IN DASHBOARD ---")
        print("1. Log in to stripe.com with the email that owns account", acct.id)
        print("2. Toggle TEST MODE on (top-right - must say 'Test mode')")
        print("3. Go to: Payments  (NOT Orders, NOT Connect)")
        print("4. Search:", pis.data[0].id if pis.data else "pi_...")
        print("5. Direct link pattern: https://dashboard.stripe.com/test/payments/" + (pis.data[0].id if pis.data else ""))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
