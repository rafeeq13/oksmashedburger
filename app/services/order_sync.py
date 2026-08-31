"""After checkout — push the same order + charges to Square, Uber, etc."""
from flask import current_app

from app.extensions import db
from app.integrations import square_gateway
from app.services.delivery import dispatch


def sync_order_integrations(order, payment_result=None):
    """Sync order number + full charge breakdown to each enabled provider."""
    store = order.store
    if not store or not order.number:
        return {}

    stripe_ref = payment_result.get("reference") if payment_result else None
    results = {}

    if square_gateway.is_enabled(store):
        sq = square_gateway.push_order(store, order, stripe_ref=stripe_ref)
        results["square"] = sq
        ref = sq.get("reference")
        if ref and sq.get("status") in ("synced", "simulated", "partial"):
            order.square_order_id = ref
        if sq.get("status") == "failed":
            current_app.logger.warning("Square sync failed for %s: %s",
                                       order.number, sq.get("raw"))

    if order.order_type == "delivery" and not order.delivery:
        results["delivery"] = dispatch(order)

    if results:
        db.session.commit()
    return results
