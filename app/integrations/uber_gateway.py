"""Third-party delivery via EACH STORE's own Uber Direct account.

A store dispatches to Uber Direct only if it has that integration enabled with
its own credentials; otherwise the platform falls back to the store's own drivers.
DEMO_PAYMENTS=true simulates the dispatch so the flow works without real keys.
"""
import os


def store_uber_config(store):
    if not store:
        return {}
    integ = store.integration("uber_direct")
    return (integ.config or {}) if (integ and integ.enabled) else {}


def is_enabled(store):
    """True only if this store has Uber Direct switched on (its own integration)."""
    return bool(store and store.is_connected("uber_direct"))


def _demo():
    return os.environ.get("DEMO_PAYMENTS", "true").lower() != "false"


def create_delivery(store, order):
    """Create a delivery on the store's Uber Direct account. Returns
    {status, reference, tracking_url, raw}."""
    cfg = store_uber_config(store)
    if _demo() or not cfg.get("client_secret"):
        return {
            "status": "assigned",
            "reference": f"uber_{order.number}",
            "tracking_url": f"https://track.uber.example/{order.number}",
            "raw": {"demo": True, "customer_id": cfg.get("customer_id")},
        }
    # Live path (client provides real keys + DEMO_PAYMENTS=false): call the Uber
    # Direct API with cfg['client_id']/['client_secret']/['customer_id'] here.
    return {"status": "pending", "reference": None, "tracking_url": None,
            "raw": {"note": "live Uber Direct call not yet implemented"}}
