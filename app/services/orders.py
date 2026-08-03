"""Order lifecycle (SRS FR-6.2) + queries used by KDS and tracking."""
from app.extensions import db
from app.models.order import Order

# Customer-facing tracker stages (the 6-step stepper).
TRACK_STAGES = ["placed", "confirmed", "preparing", "ready", "out_for_delivery", "completed"]

STAGE_META = {
    "placed":           {"label": "Order placed",      "headline": "We've got your order!",        "icon": "receipt",      "desc": "Sending your order to the kitchen."},
    "confirmed":        {"label": "Confirmed",         "headline": "Your order is confirmed",      "icon": "circle-check", "desc": "The store accepted your order and is getting started."},
    "preparing":        {"label": "Preparing",         "headline": "Your order is being prepared", "icon": "kitchen-set",  "desc": "Our crew is smashing patties and building your order fresh."},
    "ready":            {"label": "Ready",             "headline": "Your order is ready",          "icon": "bag-shopping", "desc": "Hot, packed and ready to go."},
    "out_for_delivery": {"label": "Out for delivery",  "headline": "Your order is on the way",     "icon": "car",          "desc": "Your driver is heading your way right now."},
    "completed":        {"label": "Delivered",         "headline": "Enjoy your meal!",             "icon": "house",        "desc": "Your order is complete. Thanks for choosing OK Smashed Burger!"},
    "cancelled":        {"label": "Cancelled",         "headline": "Order cancelled",              "icon": "circle-xmark", "desc": "This order was cancelled."},
}


def _flow(order_type):
    if order_type == "delivery":
        return ["placed", "confirmed", "preparing", "ready", "out_for_delivery", "completed"]
    return ["placed", "confirmed", "preparing", "ready", "completed"]  # pickup


def stage_index(status):
    if status == "cancelled":
        return -1
    try:
        return TRACK_STAGES.index(status)
    except ValueError:
        return 0


def next_status(status, order_type="delivery"):
    flow = _flow(order_type)
    if status not in flow:
        return status
    return flow[min(flow.index(status) + 1, len(flow) - 1)]


def _notify(order):
    # Local import avoids a circular import at module load.
    from app.services.notifications import notify_order_event
    notify_order_event(order, order.status)


def advance(order):
    order.status = next_status(order.status, order.order_type)
    db.session.commit()
    _notify(order)
    return order


def set_status(order, status):
    order.status = status
    db.session.commit()
    _notify(order)
    return order


def active_orders_for_store(store_id):
    return (Order.query
            .filter(Order.store_id == store_id, Order.status.notin_(["completed", "cancelled"]))
            .order_by(Order.created_at.asc())
            .all())


def orders_for_user(user_id):
    return Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
