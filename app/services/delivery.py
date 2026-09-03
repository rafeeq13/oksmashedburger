"""Dispatch a delivery order: Uber Direct if the store has it enabled, else the
store's own drivers (SRS FR-8.1 / FR-8.2)."""
import json
from datetime import datetime, timezone

from app.extensions import db
from app.models.delivery import Driver, Delivery
from app.integrations import uber_gateway as uber


def _uber_error_note(raw):
    if not raw:
        return ""
    try:
        text = json.dumps(raw, default=str)
    except Exception:
        text = str(raw)
    return text[:250]


def _apply_uber_result(delivery, res):
    delivery.status = res.get("status") or "failed"
    delivery.provider_ref = res.get("reference")
    delivery.tracking_url = res.get("tracking_url")
    if delivery.status == "failed":
        delivery.proof = _uber_error_note(res.get("raw"))


def retry_uber_dispatch(order):
    """Re-attempt Uber Direct for a failed delivery with no provider_ref."""
    if order.order_type != "delivery" or not uber.is_enabled(order.store):
        return None
    delivery = order.delivery
    if delivery and delivery.provider_ref:
        return delivery
    res = uber.create_delivery(order.store, order)
    now = datetime.now(timezone.utc)
    if not delivery:
        delivery = Delivery(
            order=order,
            method="uber_direct",
            fee=order.delivery_fee,
            assigned_at=now,
        )
        db.session.add(delivery)
    else:
        delivery.method = "uber_direct"
        delivery.assigned_at = delivery.assigned_at or now
    _apply_uber_result(delivery, res)
    db.session.commit()
    return delivery


def dispatch(order):
    if order.order_type != "delivery":
        return None
    if order.delivery:  # already dispatched
        return order.delivery

    store = order.store
    now = datetime.now(timezone.utc)

    if uber.is_enabled(store):
        res = uber.create_delivery(store, order)
        d = Delivery(order=order, method="uber_direct", fee=order.delivery_fee, assigned_at=now)
        _apply_uber_result(d, res)
    else:
        driver = Driver.query.filter_by(store_id=store.id, is_active=True, is_online=True).first()
        d = Delivery(order=order, method="own", driver=driver,
                     status="assigned" if driver else "pending",
                     fee=order.delivery_fee, assigned_at=now if driver else None)

    db.session.add(d)
    db.session.commit()
    return d
