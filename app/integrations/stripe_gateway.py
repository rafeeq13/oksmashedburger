"""Payments routed through EACH STORE's own Stripe account.

Sandbox vs production is controlled per store (`integration_env`). Sandbox uses
test keys when provided; production always calls Stripe with live keys.
"""
from app.integrations.config import active_integration_config, integration_enabled, integration_env, should_simulate


def store_stripe_config(store):
    if not store or not integration_enabled(store, "stripe"):
        return {}
    return active_integration_config(store, "stripe")


def is_connected(store):
    cfg = store_stripe_config(store)
    return bool((cfg.get("secret_key") or "").strip())


def stripe_checkout_mode(store):
    """How checkout should collect card payment for this store."""
    cfg = store_stripe_config(store)
    if should_simulate(store, "stripe", cfg):
        return "demo"
    if (cfg.get("publishable_key") or "").strip() and (cfg.get("secret_key") or "").strip():
        return "elements"
    return "off"


def _demo_result(store, amount, metadata=None):
    cfg = store_stripe_config(store)
    account = cfg.get("account_id")
    return {
        "status": "succeeded",
        "reference": "demo_pi_%s" % (account or "unset"),
        "client_secret": None,
        "account": account,
        "raw": {"demo": True, "store_account": account, "amount": amount, "metadata": metadata or {}},
    }


def create_payment_intent(store, amount, currency="usd", metadata=None):
    """Create a PaymentIntent for Stripe Elements confirmation on the client."""
    cfg = store_stripe_config(store)
    account = cfg.get("account_id")

    if should_simulate(store, "stripe", cfg):
        return _demo_result(store, amount, metadata)

    secret = (cfg.get("secret_key") or "").strip()
    if not secret:
        return {
            "status": "failed",
            "reference": None,
            "client_secret": None,
            "account": account,
            "raw": {"error": "Stripe secret key missing for production mode"},
        }

    try:
        import stripe
        stripe.api_key = secret
        intent = stripe.PaymentIntent.create(
            amount=int(round(amount * 100)),
            currency=currency,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            metadata=metadata or {},
        )
        return {
            "status": "pending",
            "reference": intent.id,
            "client_secret": intent.client_secret,
            "account": account,
            "raw": {},
        }
    except Exception as exc:  # pragma: no cover
        return {
            "status": "failed",
            "reference": None,
            "client_secret": None,
            "account": account,
            "raw": {"error": str(exc)},
        }


def verify_payment_intent(store, intent_id, expected_amount, currency="usd"):
    """Confirm a client-confirmed PaymentIntent matches the order total."""
    cfg = store_stripe_config(store)
    account = cfg.get("account_id")

    if should_simulate(store, "stripe", cfg):
        if intent_id and str(intent_id).startswith("demo_pi_"):
            return _demo_result(store, expected_amount)
        return _demo_result(store, expected_amount)

    secret = (cfg.get("secret_key") or "").strip()
    if not secret:
        return {
            "status": "failed",
            "reference": None,
            "account": account,
            "raw": {"error": "Stripe secret key missing for production mode"},
        }

    try:
        import stripe
        stripe.api_key = secret
        intent = stripe.PaymentIntent.retrieve(intent_id)
        if intent.status != "succeeded":
            return {
                "status": intent.status or "failed",
                "reference": intent.id,
                "account": account,
                "raw": {"error": "Payment not completed", "status": intent.status},
            }
        expected_cents = int(round(expected_amount * 100))
        if int(intent.amount) != expected_cents:
            return {
                "status": "failed",
                "reference": intent.id,
                "account": account,
                "raw": {"error": "Payment amount mismatch",
                        "expected_cents": expected_cents, "paid_cents": int(intent.amount)},
            }
        return {"status": "succeeded", "reference": intent.id, "account": account, "raw": {}}
    except Exception as exc:  # pragma: no cover
        return {"status": "failed", "reference": None, "account": account, "raw": {"error": str(exc)}}


def update_payment_intent(store, intent_id, metadata=None, description=None,
                          receipt_email=None, shipping=None, statement_descriptor_suffix=None):
    """Attach full order details to a PaymentIntent after checkout."""
    cfg = store_stripe_config(store)
    account = cfg.get("account_id")

    if should_simulate(store, "stripe", cfg):
        return {"status": "ok", "reference": intent_id, "account": account, "raw": {"demo": True}}

    secret = (cfg.get("secret_key") or "").strip()
    if not secret or not intent_id:
        return {
            "status": "failed",
            "reference": intent_id,
            "account": account,
            "raw": {"error": "Stripe secret key missing or no payment intent"},
        }

    try:
        import stripe
        stripe.api_key = secret
        kwargs = {}
        if metadata:
            kwargs["metadata"] = metadata
        if description:
            kwargs["description"] = str(description)[:1000]
        if receipt_email:
            kwargs["receipt_email"] = str(receipt_email)[:800]
        if shipping:
            kwargs["shipping"] = shipping
        if statement_descriptor_suffix:
            kwargs["statement_descriptor_suffix"] = str(statement_descriptor_suffix)[:22]
        intent = stripe.PaymentIntent.modify(intent_id, **kwargs)
        return {"status": "ok", "reference": intent.id, "account": account, "raw": {}}
    except Exception as exc:  # pragma: no cover
        return {"status": "failed", "reference": intent_id, "account": account, "raw": {"error": str(exc)}}


def refund_payment(store, intent_id, amount=None, currency="usd"):
    """Refund a succeeded PaymentIntent (full or partial)."""
    cfg = store_stripe_config(store)
    account = cfg.get("account_id")

    if should_simulate(store, "stripe", cfg):
        return {
            "status": "simulated",
            "reference": "demo_refund_%s" % (intent_id or "unset"),
            "account": account,
            "raw": {"demo": True, "payment_intent": intent_id, "amount": amount},
        }

    secret = (cfg.get("secret_key") or "").strip()
    if not secret or not intent_id:
        return {
            "status": "failed",
            "reference": None,
            "account": account,
            "raw": {"error": "Stripe secret key missing or no payment intent"},
        }

    try:
        import stripe
        stripe.api_key = secret
        kwargs = {"payment_intent": intent_id}
        if amount is not None:
            kwargs["amount"] = int(round(float(amount) * 100))
        refund = stripe.Refund.create(**kwargs)
        return {
            "status": "refunded",
            "reference": refund.id,
            "account": account,
            "raw": {"refund_status": refund.status},
        }
    except Exception as exc:  # pragma: no cover
        return {"status": "failed", "reference": None, "account": account, "raw": {"error": str(exc)}}


def charge(store, amount, currency="usd", metadata=None):
    """Legacy server-side charge — prefer create_payment_intent + verify_payment_intent."""
    cfg = store_stripe_config(store)
    account = cfg.get("account_id")

    if should_simulate(store, "stripe", cfg):
        return _demo_result(store, amount, metadata)

    created = create_payment_intent(store, amount, currency=currency, metadata=metadata)
    if created["status"] == "failed":
        return {"status": "failed", "reference": None, "account": account, "raw": created.get("raw") or {}}
    return {
        "status": "pending",
        "reference": created.get("reference"),
        "account": account,
        "raw": {"client_secret": created.get("client_secret"), "needs_confirmation": True},
    }
