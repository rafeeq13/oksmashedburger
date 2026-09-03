"""Order notifications via each store's SMTP (SMS still uses Twilio)."""
from app.extensions import db
from app.models.notification import Notification
from app.models import email_templates as et
from app.integrations import twilio_gateway, smtp_gateway
from app.services.mailer import sending_store
from app.services.order_details import order_email_rows
from app.services.receipts import build_receipt_attachment

# order status -> (SMS body template, template key for email)
_SMS = {
    "placed": "We got your order {n}! {store} will confirm it shortly. — {b}",
    "confirmed": "Order {n} is confirmed at {store}. We'll keep you posted. — {b}",
    "preparing": "{b}: order {n} is now being prepared at {store}.",
    "ready": "Order {n} is ready at {store}. See you soon! — {b}",
    "out_for_delivery": "Order {n} is out for delivery from {store}. Track it in your account. — {b}",
    "completed": "Order {n} complete — enjoy! Thanks for choosing {b}.",
    "cancelled": "Order {n} at {store} was cancelled. Reply or call us with any questions. — {b}",
}


def notify_order_event(order, event):
    tpl_key = et.ORDER_EVENT_KEYS.get(event)
    if not order or not tpl_key:
        return []
    store = order.store
    track_url = et.tracking_url_for(order.number)
    ctx = {
        "brand": et.BRAND,
        "store": store.name if store else et.BRAND,
        "order_number": order.number,
        "customer_name": order.customer_name or "there",
        "tracking_url": track_url,
        "order": order,
        "b": et.BRAND,
        "n": order.number,
    }
    sms_body = _SMS.get(event, "").format(**ctx)

    attachment = build_receipt_attachment(order) if tpl_key else None

    email_subject, email_plain, email_html = et.render(
        tpl_key, ctx, rows=order_email_rows(order), cta_href=track_url,
    )

    created = []
    twilio_callback = None
    if store:
        from flask import has_request_context, request
        from app.integrations.webhook_urls import resolve_webhook_url
        req_base = request.url_root.rstrip("/") if has_request_context() else None
        twilio_callback = resolve_webhook_url(store, "twilio", req_base)
        if not twilio_callback:
            try:
                from flask import url_for
                twilio_callback = url_for("webhooks.twilio_webhook", store_slug=store.slug, _external=True)
            except Exception:
                twilio_callback = None
    if store and twilio_gateway.is_enabled(store) and order.customer_phone:
        res = twilio_gateway.send_sms(store, order.customer_phone, sms_body, status_callback=twilio_callback)
        created.append(_record(order, store, "sms", "twilio",
                               order.customer_phone, None, sms_body, event, res))
    if order.customer_email:
        smtp_store = sending_store(store)
        if smtp_store and smtp_gateway.is_enabled(smtp_store):
            res = smtp_gateway.send_email(smtp_store, order.customer_email, email_subject,
                                          email_plain, attachment=attachment, html=email_html)
            created.append(_record(order, store, "email", "smtp",
                                   order.customer_email, email_subject, email_plain, event, res))
        else:
            created.append(_record(order, store, "email", "smtp",
                                   order.customer_email, email_subject, email_plain, event,
                                   {"status": "skipped",
                                    "raw": {"error": "smtp_not_configured"}}))
    if created:
        db.session.commit()
    return created


def _record(order, store, channel, provider, recipient, subject, body, event, res):
    raw = res.get("raw") or {}
    provider_ref = raw.get("sid") or "%s_%s_%s" % (provider, order.number, event)
    n = Notification(
        order_id=order.id, store_id=store.id if store else None,
        channel=channel, provider=provider, recipient=recipient, subject=subject,
        body=body, event=event, status=res.get("status", "simulated"),
        provider_ref=provider_ref,
    )
    db.session.add(n)
    print("[notify] %s -> %s via %s (%s) order %s/%s"
          % (channel, recipient, provider, n.status, order.number, event))
    return n


def recent_for_store(store_id, limit=100):
    return (Notification.query.filter_by(store_id=store_id)
            .order_by(Notification.created_at.desc()).limit(limit).all())
