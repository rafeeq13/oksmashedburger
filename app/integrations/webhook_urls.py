"""Per-store webhook endpoint URLs — editable in Admin → Integrations → Webhooks."""

WEBHOOK_PROVIDERS = [
    {
        "key": "stripe",
        "name": "Stripe",
        "icon": "credit-card",
        "secret_field": "webhook_secret",
        "secret_label": "Webhook signing secret",
        "secret_placeholder": "whsec_...",
        "events": [
            "payment_intent.succeeded",
            "payment_intent.payment_failed",
            "charge.refunded",
        ],
        "setup": "Stripe Dashboard → Developers → Webhooks → Add endpoint. Paste the URL below and select the events listed.",
    },
    {
        "key": "square",
        "name": "Square",
        "icon": "cash-register",
        "secret_field": "webhook_signature_key",
        "secret_label": "Webhook signature key",
        "secret_placeholder": "From Square Developer → Webhooks",
        "events": [
            "order.updated",
            "order.fulfillment.updated",
            "payment.updated",
            "refund.created",
        ],
        "setup": "Square Developer Dashboard → your app → Webhooks → Add subscription. Use the exact URL below (must match for signature verification).",
    },
    {
        "key": "uber_direct",
        "name": "Uber Direct",
        "icon": "car",
        "secret_field": "webhook_secret",
        "secret_label": "Webhook signing secret",
        "secret_placeholder": "From Uber Direct developer portal",
        "events": [
            "delivery.status_changed",
            "delivery.courier_update",
            "delivery.cancelled",
        ],
        "setup": "Uber Direct developer portal → Webhooks. Point delivery status updates to the URL below.",
    },
    {
        "key": "twilio",
        "name": "Twilio",
        "icon": "comment-sms",
        "secret_field": None,
        "secret_label": None,
        "events": [
            "Message status (delivered, failed, undelivered)",
        ],
        "setup": "No extra secret — Twilio validates with your Auth Token. Outbound SMS uses the status callback URL below.",
    },
]


def store_webhook_key(store):
    """Location id for webhook URLs — e.g. 7014 from 7014 Frankford Ave."""
    import re
    if not store:
        return ""
    for src in (store.address_line, getattr(store, "full_address", None), store.slug):
        if not src:
            continue
        m = re.search(r"\b(\d{4,5})\b", str(src))
        if m:
            return m.group(1)
    return store.slug


def webhook_path(provider, store_key):
    """/webhooks/7014/stripe — location first, then provider."""
    prov = provider.replace("_direct", "")
    return "/webhooks/%s/%s" % (store_key, prov)


def webhook_url(provider, store, base_url):
    base = _normalize_base(base_url)
    key = store_webhook_key(store) if store else ""
    if not base or not key:
        return ""
    return base + webhook_path(provider, key)


def endpoint_url_key(provider):
    return "%s_url" % provider


def _normalize_base(base_url):
    base = (base_url or "").strip().rstrip("/")
    if base and not base.startswith(("http://", "https://")):
        base = "https://" + base
    return base


def webhook_settings(store):
    if not store:
        return {}
    from app.integrations.config import active_integration_config
    return active_integration_config(store, "webhooks")


def default_webhook_url(store, provider, request_base=None):
    base = _normalize_base(request_base)
    if not store or not base:
        return ""
    return webhook_url(provider, store, base)


def resolve_webhook_url(store, provider, request_base=None):
    """Configured URL override, else base_url + path, else request host."""
    if not store:
        return ""
    cfg = webhook_settings(store)
    custom = (cfg.get(endpoint_url_key(provider)) or "").strip()
    if custom:
        if not custom.startswith(("http://", "https://")):
            custom = _normalize_base(custom) + (custom if custom.startswith("/") else "/" + custom)
        return custom.rstrip("/")
    base = _normalize_base(cfg.get("base_url") or request_base)
    return webhook_url(provider, store, base)


def webhook_base_url(store, request_base=None):
    cfg = webhook_settings(store)
    saved = _normalize_base(cfg.get("base_url"))
    if saved:
        return saved
    return _normalize_base(request_base)
