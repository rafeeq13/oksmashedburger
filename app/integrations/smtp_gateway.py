"""Email via EACH STORE's own SMTP account (replaces SendGrid).

A store sends email only when SMTP is enabled with host + from address.
DEMO_PAYMENTS=true simulates the send so flows work without real credentials.
"""
import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def store_smtp_config(store):
    if not store:
        return {}
    integ = store.integration("smtp")
    return (integ.config or {}) if (integ and integ.enabled) else {}


def is_enabled(store):
    """True when this store has SMTP switched on with enough to connect."""
    if not store or not store.is_connected("smtp"):
        return False
    cfg = store_smtp_config(store)
    return bool((cfg.get("smtp_host") or "").strip() and (cfg.get("from_email") or "").strip())


def _demo():
    return os.environ.get("DEMO_PAYMENTS", "true").lower() != "false"


def send_email(store, to, subject, body, attachment=None, html=None, headers=None):
    """Send via the store's SMTP server. Returns {status, raw}."""
    cfg = store_smtp_config(store)
    att_name = attachment.get("filename") if attachment else None
    if _demo() or not (cfg.get("smtp_host") or "").strip():
        return {"status": "simulated",
                "raw": {"demo": True, "host": cfg.get("smtp_host"), "to": to,
                        "subject": subject, "attachment": att_name}}

    sender = (cfg.get("from_email") or "").strip()
    if not sender:
        return {"status": "failed", "raw": {"error": "no from_email configured for SMTP"}}

    from_name = (cfg.get("from_name") or "OK Smashed Burger").strip()
    host = cfg.get("smtp_host", "").strip()
    try:
        port = int(cfg.get("smtp_port") or 587)
    except (TypeError, ValueError):
        port = 587
    user = (cfg.get("smtp_user") or "").strip()
    password = cfg.get("smtp_password") or ""
    use_tls = str(cfg.get("use_tls", "1")).lower() not in ("0", "false", "no")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = "%s <%s>" % (from_name, sender) if from_name else sender
    msg["To"] = to
    if cfg.get("reply_to"):
        msg["Reply-To"] = cfg["reply_to"]
    for k, v in (headers or {}).items():
        msg[k] = v

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body or "", "plain", "utf-8"))
    if html:
        alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)

    if attachment and attachment.get("content"):
        part = MIMEApplication(attachment["content"], _subtype="pdf")
        part.add_header("Content-Disposition", "attachment",
                        filename=att_name or "attachment.pdf")
        msg.attach(part)

    try:
        if use_tls:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                if user:
                    smtp.login(user, password)
                smtp.sendmail(sender, [to], msg.as_string())
        else:
            with smtplib.SMTP_SSL(host, port, timeout=20,
                                  context=ssl.create_default_context()) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.sendmail(sender, [to], msg.as_string())
        return {"status": "sent", "raw": {"host": host, "to": to, "attachment": att_name}}
    except Exception as e:
        return {"status": "failed", "raw": {"error": "%s: %s" % (type(e).__name__, e)}}
