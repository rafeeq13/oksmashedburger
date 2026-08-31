"""Resolve per-store integration credentials for sandbox vs production."""

import re

ENV_KEYS = frozenset({"sandbox", "production"})
_SEED_STRIPE_KEY = re.compile(r"^sk_test_[a-z0-9_]+$")


def integration_env(store):
    """Active environment for this store's orders and integrations."""
    env = (getattr(store, "integration_env", None) or "sandbox").strip().lower()
    return env if env in ENV_KEYS else "sandbox"


def active_integration_config(store, provider):
    """Credentials for the store's current environment (sandbox or production)."""
    if not store:
        return {}
    integ = store.integration(provider)
    if not integ:
        return {}
    raw = dict(integ.config or {})
    env = integration_env(store)
    if env in raw and isinstance(raw.get(env), dict):
        return dict(raw[env])
    if ENV_KEYS.intersection(raw.keys()):
        return dict(raw.get(env) or {})
    # Legacy flat config (pre sandbox/production split) — shared until migrated on save.
    return {k: v for k, v in raw.items() if k not in ENV_KEYS}


def integration_enabled(store, provider):
    integ = store.integration(provider) if store else None
    return bool(integ and integ.enabled)


def should_simulate(store, provider, cfg=None):
    """Sandbox may simulate when credentials are missing; production never simulates."""
    if not store:
        return True
    if integration_env(store) == "production":
        return False
    cfg = cfg if cfg is not None else active_integration_config(store, provider)
    if provider == "stripe":
        sk = (cfg.get("secret_key") or "").strip()
        if not sk:
            return True
        # Seed/demo keys (sk_test_south_snyder) are not real Stripe accounts.
        if integration_env(store) == "sandbox" and _SEED_STRIPE_KEY.match(sk):
            return True
        return False
    if provider == "twilio":
        return not (cfg.get("auth_token") or "").strip()
    if provider == "uber_direct":
        return not (cfg.get("client_secret") or "").strip()
    if provider == "smtp":
        from app.integrations.smtp_gateway import normalize_smtp_host
        return not normalize_smtp_host(cfg.get("smtp_host"))
    if provider == "square":
        from app.integrations.square_gateway import is_enabled as square_ready
        return not square_ready(store)
    return not cfg


def merge_env_config(integ, env, updates):
    """Write provider fields into the sandbox or production bucket."""
    raw = dict(integ.config or {})
    if not ENV_KEYS.intersection(raw.keys()):
        legacy = {k: v for k, v in raw.items() if k not in ENV_KEYS}
        if legacy:
            raw = {"sandbox": dict(legacy), "production": dict(legacy)}
        else:
            raw = {}
    bucket = dict(raw.get(env) or {})
    bucket.update(updates)
    raw[env] = bucket
    integ.config = raw
