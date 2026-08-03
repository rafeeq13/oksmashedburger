"""Order notifications, sent through EACH STORE's own Twilio (SMS) + SendGrid
(email). A store notifies on a channel only when it has that integration enabled
AND the order carries a matching recipient — so two locations can behave
differently. In demo mode every send is simulated and written to the
notifications log (SRS FR-10.x)."""
from app.extensions import db
from app.models.notification import Notification
from app.integrations import twilio_gateway, sendgrid_gateway

BRAND = "OK Smashed Burger"

# order status -> (SMS body, email subject, email body)
_TEMPLATES = {
    "placed": (
        "We got your order {n}! {store} will confirm it shortly. — {b}",
        "We received order {n}",
        "Thanks for ordering from {store}! Order {n} has been received and is awaiting confirmation."),
    "confirmed": (
        "Order {n} is confirmed at {store}. We'll keep you posted. — {b}",
        "Order {n} is confirmed",
        "Your order {n} at {store} is confirmed and heading to the kitchen."),
    "preparing": (
        "{b}: order {n} is now being prepared at {store}.",
        "Order {n} is being prepared",
        "Good news — order {n} is on the grill at {store}."),
    "ready": (
        "Order {n} is ready at {store}. See you soon! — {b}",
        "Order {n} is ready",
        "Order {n} is ready at {store}."),
    "out_for_delivery": (
        "Order {n} is out for delivery from {store}. Track it in your account. — {b}",
        "Order {n} is on the way",
        "Your order {n} from {store} is out for delivery."),
    "completed": (
        "Order {n} complete — enjoy! Thanks for choosing {b}.",
        "Order {n} complete",
        "Order {n} from {store} is complete. Thanks for choosing {b}!"),
    "cancelled": (
        "Order {n} at {store} was cancelled. Reply or call us with any questions. — {b}",
        "Order {n} cancelled",
        "Your order {n} at {store} has been cancelled."),
}


def notify_order_event(order, event):
    """Fire SMS/email for a status change, per the store's own integrations.
    Returns the list of Notification rows created (may be empty)."""
    tpl = _TEMPLATES.get(event)
    if not order or not tpl:
        return []
    store = order.store
    ctx = {"b": BRAND, "n": order.number, "store": store.name if store else BRAND}
    sms_body, email_subject, email_body = (part.format(**ctx) for part in tpl)

    # Attach the itemised PDF receipt to the order-confirmation email(s).
    attachment = None
    if event in ("placed", "confirmed"):
        try:
            from app.services.receipts import build_receipt_pdf
            attachment = {"filename": f"receipt-{order.number}.pdf", "content": build_receipt_pdf(order)}
            email_body += "\n\nYour itemised receipt is attached to this email."
        except Exception:
            attachment = None

    created = []
    if store and twilio_gateway.is_enabled(store) and order.customer_phone:
        res = twilio_gateway.send_sms(store, order.customer_phone, sms_body)
        created.append(_record(order, store, "sms", "twilio",
                               order.customer_phone, None, sms_body, event, res))
    if store and sendgrid_gateway.is_enabled(store) and order.customer_email:
        res = sendgrid_gateway.send_email(store, order.customer_email, email_subject, email_body, attachment=attachment)
        created.append(_record(order, store, "email", "sendgrid",
                               order.customer_email, email_subject, email_body, event, res))
    if created:
        db.session.commit()
    return created


def _record(order, store, channel, provider, recipient, subject, body, event, res):
    n = Notification(
        order_id=order.id, store_id=store.id if store else None,
        channel=channel, provider=provider, recipient=recipient, subject=subject,
        body=body, event=event, status=res.get("status", "simulated"),
        provider_ref=f"{provider}_{order.number}_{event}",
    )
    db.session.add(n)
    print(f"[notify] {channel} -> {recipient} via {provider} ({n.status}) "
          f"order {order.number}/{event}")
    return n


def recent_for_store(store_id, limit=100):
    return (Notification.query.filter_by(store_id=store_id)
            .order_by(Notification.created_at.desc()).limit(limit).all())
