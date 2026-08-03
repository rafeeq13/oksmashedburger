"""SMS via EACH STORE's own Twilio account.

A store sends SMS only if it has Twilio enabled with its own credentials.
DEMO_PAYMENTS=true simulates the send so the flow works without real keys.
"""
import os


def store_twilio_config(store):
    if not store:
        return {}
    integ = store.integration("twilio")
    return (integ.config or {}) if (integ and integ.enabled) else {}


def is_enabled(store):
    """True only if this store has Twilio switched on (its own integration)."""
    return bool(store and store.is_connected("twilio"))


def _demo():
    return os.environ.get("DEMO_PAYMENTS", "true").lower() != "false"


def send_sms(store, to, body):
    """Send an SMS from the store's Twilio number. Returns {status, raw}."""
    cfg = store_twilio_config(store)
    if _demo() or not cfg.get("auth_token"):
        return {"status": "simulated",
                "raw": {"demo": True, "account_sid": cfg.get("account_sid"), "to": to}}
    # Live path (client provides real keys + DEMO_PAYMENTS=false): call the Twilio
    # Messages API with cfg['account_sid']/['auth_token'] here.
    return {"status": "failed", "raw": {"note": "live Twilio call not yet implemented"}}
