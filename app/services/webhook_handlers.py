"""Process inbound integration webhooks and update orders / deliveries."""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.order import Order, Payment
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.models.webhook_event import WebhookEvent
from app.integrations.config import active_integration_config


def _trim_payload(data, limit=6000):
    try:
        raw = json.dumps(data, default=str)
    except Exception:
        raw = str(data)
    if len(raw) <= limit:
        return data if isinstance(data, dict) else {"value": data}
    return {"_truncated": True, "preview": raw[:limit]}


def log_event(store, provider, event_type, external_id=None, status="received",
              payload=None, error=None):
    row = WebhookEvent(
        store_id=store.id if store else None,
        provider=provider,
        event_type=event_type or "unknown",
        external_id=(external_id or "")[:160] or None,
        status=status,
        payload=_trim_payload(payload or {}),
        error=error,
    )
    db.session.add(row)
    return row


def _order_from_stripe_intent(intent_id, metadata=None):
    meta = metadata or {}
    number = (meta.get("order_number") or "").strip()
    if number:
        order = Order.query.filter_by(number=number).first()
        if order:
            return order
    if intent_id:
        pay = Payment.query.filter_by(provider_ref=intent_id).first()
        if pay:
            return pay.order
    return None


def _order_from_square_payload(payload):
    data = payload.get("data") or {}
    obj = data.get("object") or {}
    order = obj.get("order") or obj
    ref = (order.get("reference_id") or "").strip()
    if ref:
        found = Order.query.filter_by(number=ref).first()
        if found:
            return found
    sq_id = (order.get("id") or obj.get("id") or "").strip()
    if sq_id:
        return Order.query.filter_by(square_order_id=sq_id).first()
    return None


def _delivery_from_uber_payload(payload):
    delivery = payload.get("delivery") or payload.get("data") or payload
    ref = (
        delivery.get("id")
        or delivery.get("delivery_id")
        or payload.get("delivery_id")
        or ""
    ).strip()
    if ref:
        d = Delivery.query.filter_by(provider_ref=ref).first()
        if d:
            return d
    ext_ref = (delivery.get("external_id") or delivery.get("reference_id") or "").strip()
    if ext_ref:
        order = Order.query.filter_by(number=ext_ref).first()
        if order and order.delivery:
            return order.delivery
    return None


def _uber_status_map(status):
    from app.integrations.uber_gateway import map_uber_status
    return map_uber_status(status)


def _square_state_map(state):
    s = (state or "").strip().upper()
    return {
        "COMPLETED": "completed",
        "CANCELED": "cancelled",
        "CANCELLED": "cancelled",
    }.get(s)


def verify_square_signature(signature_key, signature_header, notification_url, body):
    key = (signature_key or "").strip()
    sig = (signature_header or "").strip()
    if not key or not sig:
        return False
    payload = (notification_url or "") + (body.decode("utf-8") if isinstance(body, bytes) else body)
    digest = hmac.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, sig)


def verify_uber_signature(secret, signature_header, body):
    sec = (secret or "").strip()
    sig = (signature_header or "").strip()
    if not sec or not sig:
        return True  # optional until Uber signing is configured
    raw = body.decode("utf-8") if isinstance(body, bytes) else body
    digest = hmac.new(sec.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, sig)


def _order_belongs_to_store(order, store):
    return bool(order and store and order.store_id == store.id)


def handle_stripe(store, event):
    if hasattr(event, "to_dict_recursive"):
        event = event.to_dict_recursive()
    elif hasattr(event, "to_dict"):
        event = event.to_dict()
    etype = event.get("type") or "unknown"
    obj = (event.get("data") or {}).get("object") or {}
    external_id = obj.get("id")

    order = _order_from_stripe_intent(external_id, obj.get("metadata") or {})
    if not _order_belongs_to_store(order, store):
        log_event(store, "stripe", etype, external_id=external_id, status="ignored",
                  payload={"reason": "order_not_found"})
        db.session.commit()
        return {"ok": True, "ignored": True}

    pay = Payment.query.filter_by(order_id=order.id).first()
    if etype == "payment_intent.succeeded":
        order.payment_status = "paid"
        if order.status in ("placed", "pending"):
            order.status = "confirmed"
        if pay:
            pay.status = "succeeded"
            pay.provider_ref = external_id or pay.provider_ref
    elif etype == "payment_intent.payment_failed":
        order.payment_status = "failed"
        if pay:
            pay.status = "failed"
    elif etype == "charge.refunded":
        prev_status = order.status
        order.payment_status = "refunded"
        if pay:
            pay.status = "refunded"
        if order.status not in ("cancelled", "completed"):
            order.status = "cancelled"
        db.session.commit()
        log_event(store, "stripe", etype, external_id=external_id, status="processed",
                  payload={"order_number": order.number})
        db.session.commit()
        if prev_status != "cancelled":
            from app.services.notifications import notify_order_event
            notify_order_event(order, "cancelled")
        return {"ok": True, "order": order.number}
    else:
        log_event(store, "stripe", etype, external_id=external_id, status="ignored",
                  payload={"reason": "unhandled_event"})
        db.session.commit()
        return {"ok": True, "ignored": True}

    db.session.commit()
    log_event(store, "stripe", etype, external_id=external_id, status="processed",
              payload={"order_number": order.number})
    db.session.commit()
    return {"ok": True, "order": order.number}


def handle_square(store, payload):
    etype = payload.get("type") or "unknown"
    external_id = (payload.get("event_id") or "")[:160]
    log_event(store, "square", etype, external_id=external_id, payload=payload)

    order = _order_from_square_payload(payload)
    if not _order_belongs_to_store(order, store):
        log_event(store, "square", etype, external_id=external_id, status="ignored",
                  payload={"reason": "order_not_found"})
        db.session.commit()
        return {"ok": True, "ignored": True}

    data = payload.get("data") or {}
    obj = data.get("object") or {}
    sq_order = obj.get("order") or obj
    mapped = _square_state_map(sq_order.get("state"))
    prev_status = order.status
    if mapped:
        order.status = mapped
    db.session.commit()
    if mapped == "cancelled" and prev_status != "cancelled":
        from app.services.notifications import notify_order_event
        notify_order_event(order, "cancelled")
    log_event(store, "square", etype, external_id=external_id, status="processed",
              payload={"order_number": order.number, "status": order.status})
    db.session.commit()
    return {"ok": True, "order": order.number}


def handle_uber(store, payload):
    etype = payload.get("event_type") or payload.get("type") or payload.get("kind") or "delivery.update"
    delivery_payload = payload.get("delivery") or payload.get("data") or payload
    external_id = (delivery_payload.get("id") or delivery_payload.get("delivery_id") or "")[:160]
    log_event(store, "uber_direct", etype, external_id=external_id, payload=payload)

    delivery = _delivery_from_uber_payload(payload)
    if not delivery or not _order_belongs_to_store(delivery.order, store):
        log_event(store, "uber_direct", etype, external_id=external_id, status="ignored",
                  payload={"reason": "delivery_not_found"})
        db.session.commit()
        return {"ok": True, "ignored": True}

    status = (
        delivery_payload.get("status")
        or delivery_payload.get("delivery_status")
        or payload.get("status")
    )
    mapped = _uber_status_map(status)
    if mapped:
        delivery.status = mapped
    tracking = delivery_payload.get("tracking_url") or delivery_payload.get("tracking_link")
    if tracking:
        delivery.tracking_url = tracking
    order = delivery.order
    if mapped == "picked_up" and order:
        order.status = "out_for_delivery"
        delivery.picked_up_at = delivery.picked_up_at or datetime.now(timezone.utc)
    elif mapped == "delivered" and order:
        order.status = "completed"
        delivery.delivered_at = delivery.delivered_at or datetime.now(timezone.utc)
    elif mapped == "failed" and order:
        prev = order.status
        order.status = "cancelled"
        if prev != "cancelled":
            from app.services.notifications import notify_order_event
            notify_order_event(order, "cancelled")

    db.session.commit()
    log_event(store, "uber_direct", etype, external_id=external_id, status="processed",
              payload={"order_number": order.number if order else None, "delivery_status": delivery.status})
    db.session.commit()
    return {"ok": True, "order": order.number if order else None}


def handle_twilio(store, form):
    etype = "message.%s" % (form.get("MessageStatus") or form.get("SmsStatus") or "unknown")
    external_id = (form.get("MessageSid") or form.get("SmsSid") or "")[:160]
    log_event(store, "twilio", etype, external_id=external_id, payload=dict(form))

    status = (form.get("MessageStatus") or form.get("SmsStatus") or "").lower()
    mapped = {"delivered": "sent", "sent": "sent", "failed": "failed",
              "undelivered": "failed"}.get(status)
    if external_id and mapped:
        note = Notification.query.filter_by(provider_ref=external_id).first()
        if note:
            note.status = mapped
            db.session.commit()
            log_event(store, "twilio", etype, external_id=external_id, status="processed",
                      payload={"notification_id": note.id})
            return {"ok": True}
    log_event(store, "twilio", etype, external_id=external_id, status="ignored",
              payload={"reason": "notification_not_found"})
    db.session.commit()
    return {"ok": True, "ignored": True}


def parse_stripe_event(store, payload, signature):
    cfg = active_integration_config(store, "stripe")
    secret = (cfg.get("webhook_secret") or "").strip()
    if not secret:
        raise ValueError("Stripe webhook secret not configured for this store")
    import stripe
    stripe.api_key = (cfg.get("secret_key") or "").strip() or None
    return stripe.Webhook.construct_event(payload, signature, secret)


def verify_twilio_request(store, url, form, signature):
    cfg = active_integration_config(store, "twilio")
    token = (cfg.get("auth_token") or "").strip()
    if not token:
        raise ValueError("Twilio auth token not configured")
    try:
        from twilio.request_validator import RequestValidator
        return RequestValidator(token).validate(url, dict(form), signature)
    except ImportError:
        current_app.logger.warning("twilio package missing - skipping signature check")
        return True
