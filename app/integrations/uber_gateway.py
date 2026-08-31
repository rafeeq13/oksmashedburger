"""Third-party delivery via EACH STORE's own Uber Direct account."""
from app.integrations.config import active_integration_config, integration_enabled, should_simulate


def store_uber_config(store):
    if not store or not integration_enabled(store, "uber_direct"):
        return {}
    return active_integration_config(store, "uber_direct")


def is_enabled(store):
    return bool(store and integration_enabled(store, "uber_direct"))


def create_delivery(store, order, payload=None):
    """Create a delivery on the store's Uber Direct account."""
    cfg = store_uber_config(store)
    from app.services.order_details import uber_payload
    order_payload = payload or uber_payload(order)
    if should_simulate(store, "uber_direct", cfg):
        return {
            "status": "assigned",
            "reference": f"uber_{order.number}",
            "tracking_url": f"https://track.uber.example/{order.number}",
            "raw": {"demo": True, "customer_id": cfg.get("customer_id"), "order": order_payload},
        }
    if not (cfg.get("client_secret") or "").strip():
        return {"status": "failed", "reference": None, "tracking_url": None,
                "raw": {"error": "Uber Direct credentials missing for production mode",
                        "order": order_payload}}
    return {"status": "pending", "reference": None, "tracking_url": None,
            "raw": {"note": "live Uber Direct call not yet implemented", "order": order_payload}}
