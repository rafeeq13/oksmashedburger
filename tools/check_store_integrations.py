"""Verify Stripe + Square for a store on production."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.models.order import Order, Payment
from app.integrations.config import active_integration_config, integration_env, should_simulate
from app.integrations import square_gateway, stripe_gateway
from app.integrations.square_gateway import _request


def check_stripe(store):
    print("\n=== STRIPE ===")
    cfg = active_integration_config(store, "stripe")
    mode = stripe_gateway.stripe_checkout_mode(store)
    sim = should_simulate(store, "stripe")
    sk = (cfg.get("secret_key") or "").strip()
    pk = (cfg.get("publishable_key") or "").strip()

    print("mode:", mode, "| simulate:", sim)
    print("account_id:", cfg.get("account_id") or "(empty)")
    print("publishable_key:", (pk[:22] + "...") if pk else "(empty)")
    print("secret_key:", (sk[:12] + "...") if sk else "(empty)")
    print("connected:", stripe_gateway.is_connected(store))

    issues = []
    if sim:
        issues.append("Stripe will SIMULATE — no real Stripe API calls (fake/seed keys)")
    elif not sk:
        issues.append("Stripe secret key missing")
    elif not pk:
        issues.append("Stripe publishable key missing")

    if not sim and sk:
        try:
            import stripe
            stripe.api_key = sk
            acct = stripe.Account.retrieve()
            print("API OK: account", acct.id)
            pis = stripe.PaymentIntent.list(limit=3)
            print("Recent payments on THIS account:")
            for pi in pis.data:
                print(" ", pi.id, pi.status, "$%.2f" % (pi.amount / 100))
        except Exception as exc:
            issues.append("Stripe API error: %s" % exc)
            print("API FAILED:", exc)

    if issues:
        print("ISSUES:")
        for i in issues:
            print(" -", i)
        return False
    print("Stripe: OK")
    return True


def check_square(store):
    print("\n=== SQUARE ===")
    cfg = active_integration_config(store, "square")
    loc = (cfg.get("location_id") or "").strip()
    app_id = (cfg.get("application_id") or "").strip()
    tok = (cfg.get("access_token") or "").strip()

    print("enabled:", square_gateway.is_enabled(store), "| simulate:", should_simulate(store, "square"))
    print("application_id:", (app_id[:30] + "...") if app_id else "(empty)")
    print("location_id:", loc or "(empty)")
    print("access_token:", (tok[:8] + "..." + tok[-4:]) if len(tok) > 12 else ("(empty)" if not tok else "(set)"))

    issues = []
    if loc.startswith("sandbox-sq0idb") or loc.startswith("sq0idb-"):
        issues.append("location_id is Application ID — use L… Location ID")
    elif loc and not loc.startswith("L"):
        issues.append("location_id should start with L")

    if not square_gateway.is_enabled(store):
        issues.append("Square not enabled — check location_id + access_token")

    print("\nSquare API — list locations:")
    resp = _request(store, "GET", "/v2/locations")
    if resp.get("errors"):
        issues.append("List locations failed: %s" % resp.get("errors"))
        print("ERROR:", resp.get("errors"))
    else:
        ids = []
        for item in resp.get("locations") or []:
            addr = item.get("address") or {}
            line = addr.get("address_line_1") or ""
            lid = item.get("id")
            ids.append(lid)
            print(" ", lid, "|", item.get("name"), "|", line, "|", item.get("status"))
            if "7014" in line or "Frankford" in (line + (item.get("name") or "")):
                print("   ^ 7014 Frankford match")

        if loc and loc not in ids:
            detail = _request(store, "GET", "/v2/locations/" + loc)
            if detail.get("errors"):
                issues.append("location_id %s not accessible: %s" % (loc, detail.get("errors")))
                print("GET /locations/%s ERROR:" % loc, detail.get("errors"))
            elif detail.get("location"):
                item = detail["location"]
                addr = item.get("address") or {}
                print("GET /locations/%s OK:" % loc, item.get("name"), addr.get("address_line_1"))

    if issues:
        print("ISSUES:")
        for i in issues:
            print(" -", i)
        return False
    print("Square: OK")
    return True


def check_recent_orders(store):
    print("\n=== RECENT ORDERS (this store) ===")
    rows = Order.query.filter_by(store_id=store.id).order_by(Order.id.desc()).limit(5).all()
    if not rows:
        print("(none)")
        return
    for o in rows:
        p = Payment.query.filter_by(order_id=o.id).first()
        ref = p.provider_ref if p else None
        demo = bool((p.raw or {}).get("demo")) if p and p.raw else False
        print(
            o.number, o.payment_status,
            "stripe=", ref, "(demo)" if demo else "",
            "square=", o.square_order_id or "NONE",
        )


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "northeast-philadelphia"
    app = create_app()
    with app.app_context():
        store = Store.query.filter_by(slug=slug, is_active=True).first()
        if not store:
            print("ERROR: store not found:", slug)
            return 1

        print("STORE:", store.name, "(%s)" % store.slug)
        print("address:", store.address_line, store.city, store.zip_code)
        print("integration_env:", integration_env(store))

        s_ok = check_stripe(store)
        q_ok = check_square(store)
        check_recent_orders(store)

        print("\n=== RESULT ===")
        print("Stripe:", "PASS" if s_ok else "FAIL")
        print("Square:", "PASS" if q_ok else "FAIL")
        return 0 if (s_ok and q_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
