"""Payments routed through EACH STORE's own Stripe account.

The store's Stripe credentials live in its `StoreIntegration` row (config JSON),
so an order placed at Center City is charged on Center City's Stripe account and
an order at Fishtown on Fishtown's — "each location has its own integrations".

DEMO_PAYMENTS=true (default) simulates a successful charge without calling Stripe,
so the whole flow works before real keys are provided. Set DEMO_PAYMENTS=false and
add real keys in each store's integration to go live.
"""
import os


def store_stripe_config(store):
    if not store:
        return {}
    integ = store.integration("stripe")
    return (integ.config or {}) if (integ and integ.enabled) else {}


def is_connected(store):
    cfg = store_stripe_config(store)
    return bool(cfg.get("secret_key"))


def _demo_mode():
    return os.environ.get("DEMO_PAYMENTS", "true").lower() != "false"


def charge(store, amount, currency="usd", metadata=None):
    """Charge `amount` (float, major units) on the store's Stripe account.

    Returns dict: {status: 'succeeded'|'pending'|'failed', reference, account, raw}.
    """
    cfg = store_stripe_config(store)
    account = cfg.get("account_id")

    # Demo / not-yet-configured: simulate success but still record which store
    # account it *would* have used, proving per-store routing.
    if _demo_mode() or not cfg.get("secret_key"):
        return {
            "status": "succeeded",
            "reference": f"demo_pi_{account or 'unset'}",
            "account": account,
            "raw": {"demo": True, "store_account": account, "amount": amount, "metadata": metadata or {}},
        }

    # Live path — uses THIS store's secret key.
    try:
        import stripe
        stripe.api_key = cfg["secret_key"]
        intent = stripe.PaymentIntent.create(
            amount=int(round(amount * 100)),
            currency=currency,
            automatic_payment_methods={"enabled": True},
            metadata=metadata or {},
        )
        # In a full UI flow the client confirms the intent with Stripe.js Elements
        # using cfg['publishable_key']; the webhook then marks it paid.
        return {"status": "pending", "reference": intent.id, "account": account,
                "raw": {"client_secret": intent.client_secret}}
    except Exception as exc:  # pragma: no cover - depends on live Stripe
        return {"status": "failed", "reference": None, "account": account, "raw": {"error": str(exc)}}
