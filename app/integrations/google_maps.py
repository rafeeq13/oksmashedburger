"""Google Maps / Places helpers — per-store API key with brand fallback."""
import os

from flask import current_app


def _key_from_config(config):
    if not config:
        return ""
    return (config.get("api_key") or config.get("key") or "").strip()


def store_google_maps_key(store):
    """Resolve the Maps JS API key for the storefront.

    Order: current store → env/brand default → any store that saved a key.
    A saved key is used even if the integration toggle was left off — admins
    often paste the key and forget to tick Enable.
    """
    if store:
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
