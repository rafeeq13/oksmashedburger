"""Audit Stripe + Square sandbox for every active store."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.integrations.config import (
    active_integration_config,
    integration_env,
    integration_enabled,
    should_simulate,
)
from app.integrations import stripe_gateway, square_gateway
from app.integrations.square_gateway import _request
from app.integrations.webhook_urls import store_webhook_key, resolve_webhook_url


def _mask(val, show=8):
    val = (val or "").strip()
    if not val:
        return "(empty)"
    if len(val) <= show + 4:
        return val[:3] + "..."
    return val[:show] + "..." + val[-4:]


def check_stripe(store):
    issues = []
    cfg = active_integration_config(store, "stripe")
    mode = stripe_gateway.stripe_checkout_mode(store)
    sim = should_simulate(store, "stripe")
    sk = (cfg.get("secret_key") or "").strip()
    pk = (cfg.get("publishable_key") or "").strip()
    wh = (cfg.get("webhook_secret") or "").strip()

    if not integration_enabled(store, "stripe"):
        issues.append("Stripe not enabled in admin")
    if sim:
        issues.append("Stripe will SIMULATE (demo) — not real sandbox API")
    elif not sk:
        issues.append("Stripe secret key missing")
    elif not pk:
        issues.append("Stripe publishable key missing")

    cfg_acct = (cfg.get("account_id") or "").strip()
    api_acct = None
    if not sim and sk:
        try:
            import stripe

            stripe.api_key = sk
            acct = stripe.Account.retrieve()
            api_acct = acct.id
        except Exception as exc:
            issues.append("Stripe API: %s" % exc)

    if api_acct and cfg_acct and cfg_acct != api_acct:
        issues.append("account_id mismatch (config %s vs API %s)" % (cfg_acct, api_acct))

    if not wh:
        issues.append("webhook_secret not set")

    return {
        "mode": mode,
        "simulate": sim,
        "account_id": cfg_acct or api_acct,
        "api_account": api_acct,
        "pk": _mask(pk, 16),
        "sk": _mask(sk, 12),
        "webhook": "set" if wh else "missing",
        "issues": issues,
    }


def check_square(store):
    issues = []
    cfg = active_integration_config(store, "square")
    loc = (cfg.get("location_id") or "").strip()
    tok = (cfg.get("access_token") or "").strip()
    app_id = (cfg.get("application_id") or "").strip()
    wh_key = (cfg.get("webhook_signature_key") or "").strip()

    if not integration_enabled(store, "square"):
        issues.append("Square not enabled in admin")
    if loc.startswith("sandbox-sq0idb") or loc.startswith("sq0idb-"):
        issues.append("location_id looks like Application ID — need L… Location ID")
    elif loc and not loc.startswith("L"):
        issues.append("location_id should start with L")
    if not square_gateway.is_enabled(store):
        issues.append("Square not ready (location_id + access_token required)")

    locations = []
    if square_gateway.is_enabled(store) and not should_simulate(store, "square"):
        resp = _request(store, "GET", "/v2/locations")
        if resp.get("errors"):
            issues.append("Square API: %s" % resp.get("errors"))
        else:
            for item in resp.get("locations") or []:
                locations.append(item.get("id"))
            if loc and loc not in locations:
                detail = _request(store, "GET", "/v2/locations/%s" % loc)
                if detail.get("errors"):
                    issues.append("location_id %s not accessible" % loc)
                else:
                    item = detail.get("location") or {}
                    locations.append("(verified %s)" % item.get("name"))

    if not wh_key:
        issues.append("webhook_signature_key not set")

    return {
        "enabled": square_gateway.is_enabled(store),
        "simulate": should_simulate(store, "square"),
        "application_id": _mask(app_id, 20),
        "location_id": loc or "(empty)",
        "token": _mask(tok, 8),
        "webhook_key": "set" if wh_key else "missing",
        "locations": len(locations),
        "issues": issues,
    }


def main():
    app = create_app()
    with app.app_context():
        stores = Store.query.filter_by(is_active=True).order_by(Store.name).all()
        base = "https://fooddeliveryaudit.com"
        print("=== ALL LOCATIONS — STRIPE + SQUARE AUDIT ===\n")
        summary = []
        for store in stores:
            env = integration_env(store)
            wh_key = store_webhook_key(store)
            print("=" * 60)
            print("%s (%s)" % (store.name, store.slug))
            print("Address: %s | webhook key: %s | env: %s" % (store.address_line, wh_key, env))
            stripe = check_stripe(store)
            square = check_square(store)
            print("\nSTRIPE: mode=%s simulate=%s acct=%s pk=%s sk=%s webhook=%s" % (
                stripe["mode"], stripe["simulate"], stripe["account_id"] or stripe["api_account"],
                stripe["pk"], stripe["sk"], stripe["webhook"],
            ))
            if stripe["api_account"]:
                print("  Stripe API account: %s" % stripe["api_account"])
            print("SQUARE: enabled=%s simulate=%s loc=%s token=%s webhook=%s" % (
                square["enabled"], square["simulate"], square["location_id"],
                square["token"], square["webhook_key"],
            ))
            print("  Webhook URLs: %s | %s" % (
                resolve_webhook_url(store, "stripe", base),
                resolve_webhook_url(store, "square", base),
            ))
            all_issues = stripe["issues"] + square["issues"]
            if all_issues:
                print("  ISSUES:")
                for i in all_issues:
                    print("   -", i)
                summary.append((store.slug, False, all_issues))
            else:
                print("  STATUS: OK")
                summary.append((store.slug, True, []))

        print("\n" + "=" * 60)
        print("SUMMARY")
        ok = [s for s, passed, _ in summary if passed]
        bad = [s for s, passed, _ in summary if not passed]
        print("PASS (%d): %s" % (len(ok), ", ".join(ok) if ok else "none"))
        print("FAIL (%d):" % len(bad))
        for slug, _, issues in summary:
            if issues:
                print("  %s:" % slug)
                for i in issues:
                    print("    -", i)
        return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
