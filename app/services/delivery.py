"""Dispatch a delivery order: Uber Direct if the store has it enabled, else the
store's own drivers (SRS FR-8.1 / FR-8.2)."""
from datetime import datetime, timezone

from app.extensions import db
from app.models.delivery import Driver, Delivery
from app.integrations import uber_gateway as uber


def dispatch(order):
    if order.order_type != "delivery":
        return None
    if order.delivery:  # already dispatched
        return order.delivery

    store = order.store
    now = datetime.now(timezone.utc)

    if uber.is_enabled(store):
        res = uber.create_delivery(store, order)
        d = Delivery(order=order, method="uber_direct", status=res["status"],
                     provider_ref=res.get("reference"), tracking_url=res.get("tracking_url"),
                     fee=order.delivery_fee, assigned_at=now)
    else:
        driver = Driver.query.filter_by(store_id=store.id, is_active=True, is_online=True).first()
        d = Delivery(order=order, method="own", driver=driver,
                     status="assigned" if driver else "pending",
                     fee=order.delivery_fee, assigned_at=now if driver else None)

    db.session.add(d)
    db.session.commit()
    return d
