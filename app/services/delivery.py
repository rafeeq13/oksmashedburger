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


def sync_delivery_from_order(order, commit=False):
    """Keep delivery row in sync when admins advance order status manually."""
    delivery = order.delivery
    if not delivery:
        return None
    now = datetime.now(timezone.utc)
    changed = False
    if order.status == "completed" and delivery.status != "delivered":
        delivery.status = "delivered"
        delivery.delivered_at = delivery.delivered_at or now
        changed = True
    elif order.status == "out_for_delivery" and delivery.status in ("pending", "assigned"):
        delivery.status = "picked_up"
        delivery.picked_up_at = delivery.picked_up_at or now
        changed = True
    elif order.status == "cancelled" and delivery.status not in ("delivered", "failed"):
        delivery.status = "failed"
        changed = True
    if changed and commit:
        db.session.commit()
    return delivery


def refresh_uber_delivery(order, commit=False):
    """Poll Uber Direct for the latest delivery status."""
    delivery = order.delivery
    if not delivery or delivery.method != "uber_direct" or not delivery.provider_ref:
        return delivery
    if not uber.is_enabled(order.store):
        return delivery
    api = uber.get_delivery(order.store, delivery.provider_ref)
    if api.get("errors") or api.get("error") or api.get("code"):
        return delivery
    mapped = uber.map_uber_status(api.get("status"))
    if not mapped:
        return delivery
    now = datetime.now(timezone.utc)
    if mapped != delivery.status:
        delivery.status = mapped
    tracking = (
        api.get("tracking_url")
        or api.get("share_url")
        or api.get("tracking_link")
        or ""
    )
    if tracking:
        delivery.tracking_url = tracking
    if mapped == "picked_up":
        delivery.picked_up_at = delivery.picked_up_at or now
    elif mapped == "delivered":
        delivery.delivered_at = delivery.delivered_at or now
    if commit:
        db.session.commit()
    return delivery


def ensure_delivery_status_current(order, commit=True):
    """Fix stale Uber rows - sync from order first, then poll Uber if needed."""
    delivery = order.delivery
    if not delivery:
        return None
    sync_delivery_from_order(order, commit=False)
    if (
        delivery.method == "uber_direct"
        and delivery.provider_ref
        and delivery.status not in ("delivered", "failed")
    ):
        refresh_uber_delivery(order, commit=False)
    if commit:
        db.session.commit()
    return delivery


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
