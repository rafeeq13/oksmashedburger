"""SMS via EACH STORE's own Twilio account.

Sandbox may simulate when credentials are missing; production requires live keys.
"""
from app.integrations.config import active_integration_config, integration_enabled, should_simulate


def store_twilio_config(store):
    if not store or not integration_enabled(store, "twilio"):
        return {}
    return active_integration_config(store, "twilio")


def is_enabled(store):
    return bool(store and integration_enabled(store, "twilio"))


def send_sms(store, to, body, status_callback=None):
    """Send an SMS from the store's Twilio number. Returns {status, raw}."""
    cfg = store_twilio_config(store)
    if should_simulate(store, "twilio", cfg):
        return {"status": "simulated",
                "raw": {"demo": True, "account_sid": cfg.get("account_sid"), "to": to}}
    # Live Twilio API
    token = (cfg.get("auth_token") or "").strip()
    account_sid = (cfg.get("account_sid") or "").strip()
    from_number = (cfg.get("from_number") or "").strip()
    if not token or not account_sid:
        return {"status": "failed", "raw": {"error": "Twilio credentials missing for production mode"}}
    try:
        from twilio.rest import Client
        client = Client(account_sid, token)
        kwargs = {"body": body, "to": to}
        if from_number:
            kwargs["from_"] = from_number
        if status_callback:
            kwargs["status_callback"] = status_callback
        msg = client.messages.create(**kwargs)
        return {"status": "sent", "raw": {"sid": msg.sid, "to": to}}
    except ImportError:
        return {"status": "failed", "raw": {"error": "twilio package not installed"}}
    except Exception as e:
        return {"status": "failed", "raw": {"error": "%s: %s" % (type(e).__name__, e)}}
