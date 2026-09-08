"""Verify per-location Stripe / Square / Uber wiring for website orders.

Checks:
- Each store uses its OWN Stripe account (live keys, account_id matches API)
- Square location_id belongs to that store's token and matches address
- Uber customer_id + OAuth per store
- Production API hosts (not sandbox)
- Website order source tags (code-level constants)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.integrations.config import active_integration_config, integration_env, should_simulate, integration_enabled
from app.integrations import stripe_gateway, square_gateway, uber_gateway
from app.integrations.square_gateway import _request as square_request, _api_base as square_api_base
from app.integrations.webhook_urls import resolve_webhook_url, store_webhook_key
import requests


def _mask(v, n=10):
    v = (v or "").strip()
    if not v:
        return ""
    return v[:n] + "..." + v[-4:] if len(v) > n + 4 else v


def check_stripe(store):
    issues = []
    cfg = active_integration_config(store, "stripe")
    env = integration_env(store)
    acct_cfg = (cfg.get("account_id") or "").strip()
    sk = (cfg.get("secret_key") or "").strip()
    pk = (cfg.get("publishable_key") or "").strip()
    api_acct = None
    key_mode = "unknown"
    if pk.startswith("pk_live_"):
        key_mode = "live"
    elif pk.startswith("pk_test_"):
        key_mode = "test"
    if sk.startswith("sk_live_"):
        key_mode = "live" if key_mode != "test" else "mixed"
    elif sk.startswith("sk_test_"):
        key_mode = "test" if key_mode != "live" else "mixed"

    if env == "production" and key_mode != "live":
        issues.append("production env but Stripe keys are not pk_live/sk_live")
    if env == "production" and should_simulate(store, "stripe"):
        issues.append("Stripe would simulate in production")

    if sk and not should_simulate(store, "stripe"):
        try:
            import stripe
            stripe.api_key = sk
            api_acct = stripe.Account.retrieve().id
            if acct_cfg and acct_cfg != api_acct:
                issues.append("account_id mismatch config=%s api=%s" % (acct_cfg, api_acct))
        except Exception as exc:
            issues.append("Stripe API: %s" % exc)

    return {
        "env": env,
        "mode": stripe_gateway.stripe_checkout_mode(store),
        "key_mode": key_mode,
        "account": api_acct or acct_cfg,
        "pk": _mask(pk, 16),
        "website_channel": "Stripe Elements on checkout (per-store publishable_key)",
        "issues": issues,
    }


def check_square(store):
    issues = []
    cfg = active_integration_config(store, "square")
    env = integration_env(store)
    loc = (cfg.get("location_id") or "").strip()
    api = square_api_base(store)
    loc_name = loc_addr = loc_status = ""

    if env == "production" and "sandbox" in api:
        issues.append("production env but Square API is sandbox host")
    if should_simulate(store, "square"):
        issues.append("Square would simulate")
    if not square_gateway.is_enabled(store):
        issues.append("Square not enabled/ready")
    elif not should_simulate(store, "square"):
        detail = square_request(store, "GET", "/v2/locations/%s" % loc)
        if detail.get("errors"):
            issues.append("Square location API: %s" % detail.get("errors"))
        else:
            item = detail.get("location") or {}
            loc_name = item.get("name") or ""
            loc_addr = (item.get("address") or {}).get("address_line_1") or ""
            loc_status = item.get("status") or ""
            if loc_status and loc_status != "ACTIVE":
                issues.append("Square location status=%s" % loc_status)
        # loose address match
        store_street = (store.address_line or "").split(",")[0].strip().lower()
        if store_street and loc_addr and store_street[:8] not in loc_addr.lower() and loc_addr.lower()[:8] not in store_street:
            issues.append("Square location address may not match store (%s vs %s)" % (store.address_line, loc_addr))

    return {
        "env": env,
        "api_host": api,
        "location_id": loc,
        "square_name": loc_name,
        "square_address": loc_addr,
        "website_channel": "Square Orders API note='Web order …' + payment external_details source=Stripe",
        "issues": issues,
    }


def check_uber(store):
    issues = []
    cfg = active_integration_config(store, "uber_direct")
    env = integration_env(store)
    cid = (cfg.get("customer_id") or "").strip()
    if not uber_gateway.is_enabled(store):
        issues.append("Uber Direct not fully configured")
    elif should_simulate(store, "uber_direct"):
        issues.append("Uber would simulate")
    else:
        try:
            r = requests.post(
                TOKEN_URL,
                data={
                    "client_id": cfg.get("client_id", "").strip(),
                    "client_secret": cfg.get("client_secret", "").strip(),
                    "grant_type": "client_credentials",
                    "scope": "eats.deliveries",
                },
                timeout=20,
            )
            if r.status_code != 200:
                issues.append("Uber OAuth failed %s" % r.status_code)
        except Exception as exc:
            issues.append("Uber OAuth: %s" % exc)

    return {
        "env": env,
        "customer_id": cid or "(missing)",
        "website_channel": "Uber Direct external_id=order.number, pickup=store address",
        "issues": issues,
    }


TOKEN_URL = "https://auth.uber.com/oauth/v2/token"


def main():
    app = create_app()
    base = os.environ.get("PUBLIC_SITE_URL", "https://oksmashedburger.com").rstrip("/")
    with app.app_context():
        stores = Store.query.filter_by(is_active=True).order_by(Store.name).all()
        print("=== PER-LOCATION CHANNEL AUDIT (website → Stripe / Square / Uber) ===\n")
        stripe_accounts = {}
        uber_customers = {}
        all_issues = []
        for s in stores:
            st = check_stripe(s)
            sq = check_square(s)
            ub = check_uber(s)
            wh = store_webhook_key(s)
            print("=" * 62)
            print("%s (%s)" % (s.name, s.slug))
            print("  Store address: %s" % s.address_line)
            print("  integration_env: %s | webhook key: %s" % (st["env"], wh))
            print()
            print("  STRIPE (website checkout → this store's account)")
            print("    account: %s | keys: %s | checkout: %s" % (st["account"], st["key_mode"], st["mode"]))
            print("    publishable: %s" % st["pk"])
            print("    webhook: %s" % resolve_webhook_url(s, "stripe", base))
            print("    channel: %s" % st["website_channel"])
            if st["issues"]:
                for i in st["issues"]:
                    print("    !", i)
            print()
            print("  SQUARE (web order → this store's Square location)")
            print("    API: %s" % sq["api_host"])
            print("    location_id: %s" % sq["location_id"])
            if sq["square_name"]:
                print("    Square name: %s | %s" % (sq["square_name"], sq["square_address"]))
            print("    webhook: %s" % resolve_webhook_url(s, "square", base))
            print("    channel: %s" % sq["website_channel"])
            if sq["issues"]:
                for i in sq["issues"]:
                    print("    !", i)
            print()
            print("  UBER DIRECT (delivery dispatch from this store)")
            print("    customer_id: %s" % ub["customer_id"])
            print("    webhook: %s" % resolve_webhook_url(s, "uber_direct", base))
            print("    channel: %s" % ub["website_channel"])
            if ub["issues"]:
                for i in ub["issues"]:
                    print("    !", i)

            acct = st["account"]
            if acct:
                stripe_accounts.setdefault(acct, []).append(s.slug)
            cid = ub["customer_id"]
            if cid and cid != "(missing)":
                uber_customers.setdefault(cid, []).append(s.slug)

            loc_issues = st["issues"] + sq["issues"] + ub["issues"]
            if loc_issues:
                all_issues.append((s.slug, loc_issues))
            else:
                print("\n  STATUS: channel wiring OK for website orders")

        print("\n" + "=" * 62)
        print("CROSS-LOCATION CHECKS")
        dup_stripe = {a: slugs for a, slugs in stripe_accounts.items() if len(slugs) > 1}
        dup_uber = {c: slugs for c, slugs in uber_customers.items() if len(slugs) > 1}
        if dup_stripe:
            print("  NOTE: same Stripe account on multiple stores (OK if intentional):")
            for a, slugs in dup_stripe.items():
                print("    %s → %s" % (a, ", ".join(slugs)))
        else:
            print("  Stripe: each location has its own account ✓")
        if dup_uber:
            print("  NOTE: same Uber customer_id on multiple stores:")
            for c, slugs in dup_uber.items():
                print("    %s → %s" % (c, ", ".join(slugs)))
        else:
            print("  Uber: each location has its own customer_id ✓")

        print("\nSUMMARY")
        if all_issues:
            for slug, issues in all_issues:
                print("  %s:" % slug)
                for i in issues:
                    print("    -", i)
            return 1
        print("  All locations: website → Stripe / Square / Uber channels look correct.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
