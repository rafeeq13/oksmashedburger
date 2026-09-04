"""Cancel a paid web order | refund Stripe, cancel Square / delivery, notify customer."""
from flask import current_app

from app.extensions import db
from app.models.order import Payment
from app.integrations import square_gateway, uber_gateway
from app.integrations.stripe_gateway import refund_payment


def cancel_order_integrations(order):
    """Reverse external side effects. Returns per-provider result dicts."""
    store = order.store
    if not store or not order:
        return {}

    results = {}
    payment = Payment.query.filter_by(order_id=order.id).first()
    intent_id = (payment.provider_ref if payment else "") or ""

    if order.payment_status == "paid" and intent_id:
        stripe_res = refund_payment(store, intent_id, amount=float(order.total or 0))
        results["stripe"] = stripe_res
        if stripe_res.get("status") == "refunded" and payment:
            payment.status = "refunded"
            order.payment_status = "refunded"
        elif stripe_res.get("status") in ("skipped", "simulated"):
            if order.payment_status == "paid":
                order.payment_status = "refunded"
            if payment:
                payment.status = "refunded"

    if order.square_order_id:
        sq_res = square_gateway.cancel_order(store, order.square_order_id)
        results["square"] = sq_res

    delivery = order.delivery
    if delivery and delivery.status not in ("delivered", "failed"):
        if delivery.method == "uber_direct" and delivery.provider_ref:
            uber_res = uber_gateway.cancel_delivery(store, delivery.provider_ref)
            results["uber"] = uber_res
        delivery.status = "failed"

    if results:
        db.session.commit()
    return results


def cancel_order(order):
    """Full cancel: integrations, status, customer notification."""
    if order.status == "cancelled":
        return order, {}

    results = cancel_order_integrations(order)
    order.status = "cancelled"
    db.session.commit()

    from app.services.notifications import notify_order_event
    notify_order_event(order, "cancelled")

    current_app.logger.info(
        "order_cancelled number=%s stripe=%s square=%s",
        order.number,
        (results.get("stripe") or {}).get("status"),
        (results.get("square") or {}).get("status"),
    )
    return order, results
