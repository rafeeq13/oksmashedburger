"""Order notifications via each store's SMTP (SMS still uses Twilio)."""
from app.extensions import db
from app.models.notification import Notification
from app.models import email_templates as et
from app.integrations import twilio_gateway, smtp_gateway

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
    ctx = {
        "brand": et.BRAND,
        "store": store.name if store else et.BRAND,
        "order_number": order.number,
        "customer_name": order.customer_name or "there",
        "b": et.BRAND,
        "n": order.number,
    }
    sms_body = _SMS.get(event, "").format(**ctx)

    attachment = None
    if event in ("placed", "confirmed"):
        try:
            from app.services.receipts import build_receipt_pdf
            attachment = {"filename": "receipt-%s.pdf" % order.number,
                          "content": build_receipt_pdf(order)}
        except Exception:
            attachment = None

    email_subject, email_plain, email_html = et.render(tpl_key, ctx)

    created = []
    if store and twilio_gateway.is_enabled(store) and order.customer_phone:
        res = twilio_gateway.send_sms(store, order.customer_phone, sms_body)
        created.append(_record(order, store, "sms", "twilio",
                               order.customer_phone, None, sms_body, event, res))
    if store and smtp_gateway.is_enabled(store) and order.customer_email:
        res = smtp_gateway.send_email(store, order.customer_email, email_subject,
                                      email_plain, attachment=attachment, html=email_html)
        created.append(_record(order, store, "email", "smtp",
                               order.customer_email, email_subject, email_plain, event, res))
    if created:
        db.session.commit()
    return created


def _record(order, store, channel, provider, recipient, subject, body, event, res):
    n = Notification(
        order_id=order.id, store_id=store.id if store else None,
        channel=channel, provider=provider, recipient=recipient, subject=subject,
        body=body, event=event, status=res.get("status", "simulated"),
        provider_ref="%s_%s_%s" % (provider, order.number, event),
    )
    db.session.add(n)
    print("[notify] %s -> %s via %s (%s) order %s/%s"
          % (channel, recipient, provider, n.status, order.number, event))
    return n


def recent_for_store(store_id, limit=100):
    return (Notification.query.filter_by(store_id=store_id)
            .order_by(Notification.created_at.desc()).limit(limit).all())
