"""Read-only production readiness check for all stores and integrations."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.integrations.config import (
    active_integration_config,
    integration_env,
    should_simulate,
    integration_enabled,
)
from app.integrations import stripe_gateway, square_gateway, uber_gateway, smtp_gateway
from app.integrations.twilio_gateway import is_enabled as twilio_enabled
from app.integrations.webhook_urls import resolve_webhook_url


def _mask(val, n=8):
    val = (val or "").strip()
    if not val:
        return "MISSING"
    if len(val) <= n + 4:
        return "set"
    return val[:n] + "..." + val[-4:]


def check_store(store, base):
    issues = []
    env = integration_env(store)
    if env != "production":
        issues.append("integration_env is %s (not production)" % env)

    # Stripe
    st = active_integration_config(store, "stripe")
    if not integration_enabled(store, "stripe"):
        issues.append("Stripe disabled")
    elif should_simulate(store, "stripe"):
        issues.append("Stripe will SIMULATE (not live)")
    else:
        if not st.get("secret_key"):
            issues.append("Stripe secret_key missing")
        if not st.get("publishable_key"):
            issues.append("Stripe publishable_key missing")
        if not st.get("webhook_secret"):
            issues.append("Stripe webhook_secret missing")
        elif not stripe_gateway.is_connected(store):
            issues.append("Stripe not connected")

    # Square
    sq = active_integration_config(store, "square")
    if not square_gateway.is_enabled(store):
        issues.append("Square not ready (token/location)")
    elif should_simulate(store, "square"):
        issues.append("Square will SIMULATE")
    else:
        loc = (sq.get("location_id") or "").strip()
        if not loc.startswith("L"):
            issues.append("Square location_id invalid: %s" % (loc or "empty"))
        if not sq.get("webhook_signature_key"):
            issues.append("Square webhook_signature_key missing (POS sync updates may fail)")

    # Uber
    if integration_enabled(store, "uber_direct"):
        ub = active_integration_config(store, "uber_direct")
        if should_simulate(store, "uber_direct"):
            issues.append("Uber Direct will SIMULATE")
        else:
            for key in ("customer_id", "client_id", "client_secret"):
                if not (ub.get(key) or "").strip():
                    issues.append("Uber %s missing" % key)

    # SMTP
    if not smtp_gateway.is_enabled(store):
        issues.append("SMTP not configured (order emails may fail)")
    elif should_simulate(store, "smtp"):
        issues.append("SMTP will SIMULATE (no real email)")

    # Webhook URLs
    stripe_url = resolve_webhook_url(store, "stripe", base)
    square_url = resolve_webhook_url(store, "square", base)
    if base not in stripe_url and "oksmashedburger.com" not in stripe_url:
        issues.append("Stripe webhook URL not on oksmashedburger.com: %s" % stripe_url)
    if base not in square_url and "oksmashedburger.com" not in square_url:
        issues.append("Square webhook URL not on oksmashedburger.com: %s" % square_url)

    return {
        "env": env,
        "stripe": {
            "mode": stripe_gateway.stripe_checkout_mode(store),
            "simulate": should_simulate(store, "stripe"),
            "connected": stripe_gateway.is_connected(store),
            "pk": _mask(st.get("publishable_key"), 16),
            "wh": "set" if st.get("webhook_secret") else "MISSING",
        },
        "square": {
            "enabled": square_gateway.is_enabled(store),
            "simulate": should_simulate(store, "square"),
            "loc": sq.get("location_id") or "MISSING",
            "wh_key": "set" if sq.get("webhook_signature_key") else "MISSING",
        },
        "uber": {
            "enabled": uber_gateway.is_enabled(store),
            "simulate": should_simulate(store, "uber_direct"),
        },
        "smtp": {
            "enabled": smtp_gateway.is_enabled(store),
            "simulate": should_simulate(store, "smtp"),
            "host": active_integration_config(store, "smtp").get("smtp_host") or "MISSING",
        },
        "twilio": twilio_enabled(store),
        "webhooks": {"stripe": stripe_url, "square": square_url, "uber": resolve_webhook_url(store, "uber_direct", base)},
        "issues": issues,
    }


def main():
    app = create_app()
    base = os.environ.get("PUBLIC_SITE_URL", "https://oksmashedburger.com").rstrip("/")
    with app.app_context():
        stores = Store.query.filter_by(is_active=True).order_by(Store.name).all()
        print("=== PRODUCTION ORDER READINESS (no order placed) ===")
        print("Site base:", base)
        print("Stores:", len(stores), "\n")
        all_ok = True
        for store in stores:
            r = check_store(store, base)
            print("=" * 60)
            print("%s (%s) | env=%s" % (store.name, store.slug, r["env"]))
            print("  Orders: accepting=%s" % store.accepting_orders)
            print("  STRIPE: mode=%s live=%s connected=%s webhook=%s" % (
                r["stripe"]["mode"], not r["stripe"]["simulate"], r["stripe"]["connected"], r["stripe"]["wh"]))
            print("  SQUARE: ready=%s live=%s loc=%s webhook_key=%s" % (
                r["square"]["enabled"], not r["square"]["simulate"], r["square"]["loc"], r["square"]["wh_key"]))
            print("  UBER:   enabled=%s live=%s" % (r["uber"]["enabled"], not r["uber"]["simulate"]))
            print("  SMTP:   ready=%s live=%s host=%s" % (r["smtp"]["enabled"], not r["smtp"]["simulate"], r["smtp"]["host"]))
            print("  TWILIO: %s" % ("enabled" if r["twilio"] else "off/disabled"))
            print("  WEBHOOKS:")
            print("    stripe:", r["webhooks"]["stripe"])
            print("    square:", r["webhooks"]["square"])
            print("    uber:  ", r["webhooks"]["uber"])
            if r["issues"]:
                all_ok = False
                print("  BLOCKERS / WARNINGS:")
                for i in r["issues"]:
                    print("   -", i)
            else:
                print("  STATUS: READY for live test order")
        print("\n" + "=" * 60)
        if all_ok:
            print("OVERALL: All locations look ready for a live test order.")
        else:
            print("OVERALL: Fix warnings above before relying on full order flow.")
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
