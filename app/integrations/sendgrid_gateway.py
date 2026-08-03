"""Email via EACH STORE's own SendGrid account.

A store sends email only if it has SendGrid enabled with its own API key.
DEMO_PAYMENTS=true simulates the send so the flow works without real keys.
"""
import base64
import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.sendgrid.com/v3/mail/send"
TIMEOUT = 15


def store_sendgrid_config(store):
    if not store:
        return {}
    integ = store.integration("sendgrid")
    return (integ.config or {}) if (integ and integ.enabled) else {}


def is_enabled(store):
    """True only if this store has SendGrid switched on (its own integration)."""
    return bool(store and store.is_connected("sendgrid"))


def _demo():
    return os.environ.get("DEMO_PAYMENTS", "true").lower() != "false"


def send_email(store, to, subject, body, attachment=None, html=None, headers=None):
    """Send an email from the store's SendGrid account.

    `attachment` is an optional dict {"filename": str, "content": bytes} — e.g. the
    PDF receipt attached to an order-confirmation email.
    `html` is an optional HTML alternative; `body` is always sent as the plain-text
    part so clients that block HTML still get a readable message.
    `headers` adds raw SMTP headers — used for List-Unsubscribe on bulk mail,
    which is what makes Gmail and Outlook show their own one-click unsubscribe.
    Returns {status, raw}.
    """
    cfg = store_sendgrid_config(store)
    att_name = attachment.get("filename") if attachment else None
    if _demo() or not cfg.get("api_key"):
        return {"status": "simulated",
                "raw": {"demo": True, "from": cfg.get("from_email"), "to": to,
                        "subject": subject, "attachment": att_name}}

    sender = cfg.get("from_email")
    if not sender:
        return {"status": "failed",
                "raw": {"error": "no from_email configured for this store"}}

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": sender, "name": cfg.get("from_name") or "OK Smashed Burger"},
        "subject": subject,
        # SendGrid requires the parts in ascending order of preference, so
        # text/plain must come before text/html.
        "content": ([{"type": "text/plain", "value": body}]
                    + ([{"type": "text/html", "value": html}] if html else [])),
    }
    if cfg.get("reply_to"):
        payload["reply_to"] = {"email": cfg["reply_to"]}
    if headers:
        payload["headers"] = dict(headers)
    if attachment and attachment.get("content"):
        payload["attachments"] = [{
            "filename": att_name,
            "type": "application/pdf",
            "disposition": "attachment",
            "content": base64.b64encode(attachment["content"]).decode("ascii"),
        }]

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer %s" % cfg["api_key"],
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            # a successful Mail Send is 202 with an empty body
            return {"status": "sent",
                    "raw": {"http": res.status,
                            "message_id": res.headers.get("X-Message-Id"),
                            "to": to, "attachment": att_name}}
    except urllib.error.HTTPError as e:
        # SendGrid puts the reason in the body — keep it, it is what makes a
        # rejected sender or a bad key diagnosable from the notifications log.
        detail = e.read().decode("utf-8", "replace")[:400]
        return {"status": "failed", "raw": {"http": e.code, "error": detail}}
    except Exception as e:                       # DNS, TLS, timeout
        return {"status": "failed", "raw": {"error": "%s: %s" % (type(e).__name__, e)}}
