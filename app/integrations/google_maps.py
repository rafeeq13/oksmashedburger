"""Google Maps / Places helpers | per-store API key with brand fallback."""
import os

from flask import current_app

from app.integrations.config import active_integration_config, integration_enabled


def _key_from_config(config):
    if not config:
        return ""
    return (config.get("api_key") or config.get("key") or "").strip()


def store_google_maps_key(store):
    """Resolve the Maps JS API key for the storefront."""
    if store:
        if integration_enabled(store, "google_maps"):
            key = _key_from_config(active_integration_config(store, "google_maps"))
            if key:
                return key
        integ = store.integration("google_maps")
        if integ:
            key = _key_from_config(integ.config)
            if key:
                return key

    env_key = (os.environ.get("GOOGLE_MAPS_API_KEY")
               or current_app.config.get("GOOGLE_MAPS_API_KEY", "")
               or "").strip()
    if env_key:
        return env_key

    try:
        from app.models.store import StoreIntegration
        for integ in StoreIntegration.query.filter_by(provider="google_maps").all():
            key = _key_from_config(integ.config)
            if key:
                return key
    except Exception:
        pass
    return ""
