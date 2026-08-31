"""Email via EACH STORE's own SMTP account.

Sandbox may simulate when SMTP is not configured; production requires live SMTP.
"""
import re
import smtplib
import socket
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.integrations.config import active_integration_config, integration_enabled, should_simulate

_HOST_SCHEME_RE = re.compile(r"^(?:smtp|smtps|https?|mailto)://", re.I)
_INVALID_PLACEHOLDER_HOSTS = frozenset({"smtp", "mail", "email", "server"})


def normalize_smtp_host(raw):
    """Strip common mistakes (scheme, path, port, whitespace) from SMTP host input."""
    host = (raw or "").strip()
    if not host:
        return ""
    host = _HOST_SCHEME_RE.sub("", host)
    host = host.split("/")[0].strip()
    if host.startswith("[") and "]" in host:
        host = host[1:host.index("]")]
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    return host.strip().rstrip(".").lower()


def smtp_host_warnings(host):
    """Non-blocking hints when a host looks wrong or does not resolve."""
    host = normalize_smtp_host(host)
    if not host:
        return []
    warnings = []
    if host in _INVALID_PLACEHOLDER_HOSTS:
        warnings.append(
            "'%s' is not a mail server hostname — use e.g. smtp.gmail.com, "
            "smtp.office365.com, or mail.privateemail.com" % host
        )
    elif "." not in host:
        warnings.append("'%s' does not look like a domain name (no dot)" % host)
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        warnings.append("Could not resolve '%s' — check spelling or DNS" % host)
    return warnings


def store_smtp_config(store):
    if not store or not integration_enabled(store, "smtp"):
        return {}
    return active_integration_config(store, "smtp")


def is_enabled(store):
    """True when this store has SMTP switched on with enough to connect."""
    if not store or not integration_enabled(store, "smtp"):
        return False
    cfg = store_smtp_config(store)
    return bool(normalize_smtp_host(cfg.get("smtp_host")) and (cfg.get("from_email") or "").strip())


def send_email(store, to, subject, body, attachment=None, html=None, headers=None):
    """Send via the store's SMTP server. Returns {status, raw}."""
    cfg = store_smtp_config(store)
    att_name = attachment.get("filename") if attachment else None
    host = normalize_smtp_host(cfg.get("smtp_host"))
    if should_simulate(store, "smtp", cfg) or not host:
        if not host and not should_simulate(store, "smtp", cfg):
            return {"status": "failed", "raw": {"error": "SMTP host missing for production mode"}}
        return {"status": "simulated",
                "raw": {"error": "SMTP not configured", "to": to, "subject": subject,
                        "attachment": att_name}}

    sender = (cfg.get("from_email") or "").strip()
    if not sender:
        return {"status": "failed", "raw": {"error": "no from_email configured for SMTP"}}

    from_name = (cfg.get("from_name") or "OK Smashed Burger").strip()
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
