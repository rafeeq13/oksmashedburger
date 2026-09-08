"""Test Stripe webhook setup for a store. Usage: python tools/test_stripe_webhook.py northeast-philadelphia"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.models.order import Order, Payment
from app.models.webhook_event import WebhookEvent
from app.integrations.config import active_integration_config, integration_env
from app.integrations.webhook_urls import resolve_webhook_url, webhook_settings, default_webhook_url
from app.services import webhook_handlers as wh


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "northeast-philadelphia"
    app = create_app()
    with app.app_context():
        store = Store.query.filter_by(slug=slug).first()
        if not store:
            print("STORE NOT FOUND:", slug)
            return 1

        cfg = active_integration_config(store, "stripe")
        wh_cfg = webhook_settings(store)
        base = os.environ.get("PUBLIC_SITE_URL", "https://oksmashedburger.com").rstrip("/")
        resolved = resolve_webhook_url(store, "stripe", base)
        default = default_webhook_url(store, "stripe", base)

        print("=== STRIPE WEBHOOK TEST ===")
        print("store:", store.name, "|", store.slug, "| env:", integration_env(store))
        print("stripe_account:", cfg.get("account_id"))
        print("secret_key:", "yes" if (cfg.get("secret_key") or "").strip() else "NO")
        print("webhook_secret:", "yes" if (cfg.get("webhook_secret") or "").strip() else "NO")
        print("webhook_base_url:", wh_cfg.get("base_url") or "(auto)")
        print("stripe_url_override:", wh_cfg.get("stripe_url") or "(none)")
        print("resolved_endpoint:", resolved)
        print("default_endpoint:", default)

        order = Order.query.filter_by(store_id=store.id).order_by(Order.id.desc()).first()
        if not order:
            print("NO ORDERS for store")
            return 2
        pay = Payment.query.filter_by(order_id=order.id).first()
        pi_id = pay.provider_ref if pay else None
        print("\nlatest_order:", order.number, "| payment:", order.payment_status, "| pi:", pi_id)

        # Simulate payment_intent.succeeded webhook payload
        fake_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": pi_id or "pi_test_webhook",
                    "metadata": {"order_number": order.number, "store": store.slug},
                }
            },
        }

        print("\n--- handler dry-run (no stripe signature) ---")
        if pi_id and not str(pi_id).startswith("demo_pi"):
            before = order.payment_status
            result = wh.handle_stripe(store, fake_event)
            print("handler_result:", result)
            from app.extensions import db
            db.session.refresh(order)
            print("order_after:", order.number, order.payment_status, "(was %s)" % before)
        else:
            print("skip handler, no real payment intent on latest order")

        # List Stripe webhook endpoints via API if secret key present
        sk = (cfg.get("secret_key") or "").strip()
        if sk and not sk.startswith("sk_test_south"):
            import stripe
            stripe.api_key = sk
            print("\n--- STRIPE DASHBOARD WEBHOOKS ---")
            try:
                endpoints = stripe.WebhookEndpoint.list(limit=10)
                for ep in endpoints.data:
                    print(ep.id, "|", ep.status, "|", ep.url)
                    if resolved and ep.url.rstrip("/") == resolved.rstrip("/"):
                        print("  ^ MATCHES our resolved endpoint")
            except Exception as exc:
                print("stripe list failed:", exc)

        print("\n--- RECENT WEBHOOK EVENTS (stripe) ---")
        events = (
            WebhookEvent.query.filter_by(store_id=store.id, provider="stripe")
            .order_by(WebhookEvent.id.desc())
            .limit(5)
            .all()
        )
        if not events:
            print("(none yet)")
        for ev in events:
            print(ev.created_at, ev.event_type, ev.status, ev.external_id or "", ev.error or "")

        ok = bool((cfg.get("webhook_secret") or "").strip()) and bool(resolved)
        print("\nRESULT:", "READY" if ok else "NEEDS SETUP")
        if not (cfg.get("webhook_secret") or "").strip():
            print("  -> Add webhook signing secret in Admin → Integrations → Webhooks → Stripe")
        if not resolved:
            print("  -> Webhook URL could not be resolved")

        if "--http-test" in sys.argv and (cfg.get("webhook_secret") or "").strip() and resolved:
            import time
            import stripe
            import urllib.request
            test_order = order
            payload_dict = {
                "id": "evt_test_webhook_%d" % int(time.time()),
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": pi_id or "pi_test_webhook",
                        "metadata": {
                            "order_number": test_order.number,
                            "store": store.slug,
                        },
                    }
                },
            }
            payload = json.dumps(payload_dict)
            secret = cfg.get("webhook_secret").strip()
            if hasattr(stripe, "WebhookSignature") and hasattr(
                stripe.WebhookSignature, "generate_test_header_string"
            ):
                sig = stripe.WebhookSignature.generate_test_header_string(
                    payload=payload, secret=secret
                )
            elif hasattr(stripe, "WebhookSignature") and hasattr(
                stripe.WebhookSignature, "generate_signature_header"
            ):
                sig = stripe.WebhookSignature.generate_signature_header(payload, secret)
            else:
                raise RuntimeError("Stripe SDK missing webhook test header helper")
            req = urllib.request.Request(
                resolved,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json", "Stripe-Signature": sig},
                method="POST",
            )
            print("\n--- LIVE HTTP TEST ---", resolved)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = resp.read().decode("utf-8")
                    print("http", resp.status, body)
            except Exception as exc:
                print("http FAILED:", exc)

        return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
