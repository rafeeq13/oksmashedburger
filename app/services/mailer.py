"""Site-level email (no order attached), sent via each store's SMTP.

Order status mail lives in notifications.py. Template copy is editable in
/admin/email-templates; delivery uses /admin/integrations → SMTP.
"""
from flask import url_for

from app.extensions import db
from app.integrations import smtp_gateway
from app.services.email_delivery import is_blocked, is_valid_email
from app.models.notification import Notification
from app.models.store import Store
from app.models import email_templates as et


def sending_store(preferred=None):
    """The store whose SMTP account carries this message."""
    if preferred is not None and smtp_gateway.is_enabled(preferred):
        return preferred
    try:
        from app.helpers import get_current_store
        current = get_current_store()
        if current is not None and smtp_gateway.is_enabled(current):
            return current
    except Exception:
        pass
    for s in Store.query.filter_by(is_active=True).order_by(Store.id).all():
        if smtp_gateway.is_enabled(s):
            return s
    return preferred or Store.query.order_by(Store.id).first()


def business_inbox(store=None):
    store = store or sending_store()
    addr = ""
    if store and store.email:
        addr = (store.email or "").strip()
    if not addr:
        cfg = smtp_gateway.store_smtp_config(store)
        addr = (cfg.get("from_email") or "").strip()
    if not is_valid_email(addr) or is_blocked(addr):
        return ""
    return addr


def send(to, subject, body, event, store=None, attachment=None, html=None, headers=None):
    to = (to or "").strip()
    if not to:
        return {"status": "skipped", "raw": {"error": "no recipient"}}
    if is_blocked(to) or not is_valid_email(to):
        print("[mail] %s -> %s (skipped: blocked or invalid address)" % (event, to))
        return {"status": "skipped", "raw": {"error": "recipient_blocked_or_invalid", "to": to}}
    store = sending_store(store)
    if not smtp_gateway.is_enabled(store):
        db.session.add(Notification(
            order_id=None, store_id=store.id if store else None,
            channel="email", provider="smtp", recipient=to,
            subject=subject[:160], body=body, event=event[:30],
            status="skipped",
            provider_ref="site_%s_%s" % (event, to)))
        db.session.commit()
        print("[mail] %s -> %s (skipped: smtp not configured)" % (event, to))
        return {"status": "skipped", "raw": {"error": "smtp_not_configured"}}
    res = smtp_gateway.send_email(store, to, subject, body,
                                  attachment=attachment, html=html, headers=headers)
    db.session.add(Notification(
        order_id=None, store_id=store.id if store else None,
        channel="email", provider="smtp", recipient=to,
        subject=subject[:160], body=body, event=event[:30],
        status=res.get("status", "simulated"),
        provider_ref="site_%s_%s" % (event, to)))
    db.session.commit()
    print("[mail] %s -> %s (%s)" % (event, to, res.get("status")))
    return res


def _abs(path):
    from app.helpers import public_site_url
    return public_site_url(path)


def contact_received(msg, store=None):
    kind = msg.subject or "Enquiry"
    rows = [("From", msg.name or "n/a"), ("Email", msg.email or "n/a"),
            ("Order number", msg.order_number), ("Message", msg.message)]
    store_name = store.name if store else et.BRAND

    to_business = business_inbox(store)
    if to_business:
        ctx = {
            "store": store_name,
            "subject": kind,
            "message": msg.message or "",
            "customer_name": msg.name or msg.email or "website",
        }
        subj, plain, html = et.render(
            "contact_new", ctx, rows=rows, cta_href=_abs("/admin"),
        )
        send(to_business, subj, plain, event="contact_new", store=store, html=html)

    if msg.email:
        first = msg.name.split(" ")[0] if msg.name else "there"
        ctx = {"store": store_name, "subject": kind,
               "message": msg.message or "", "customer_name": first}
        subj, plain, html = et.render("contact_ack", ctx,
                                      rows=[("Subject", kind), ("What you sent", msg.message)],
                                      cta_href=_abs("/menu"))
        send(msg.email, subj, plain, event="contact_ack", store=store, html=html)


def contact_reply(msg, reply_body, store=None):
    """Email the customer after an admin replies in /admin/messages."""
    if not msg.email:
        return {"status": "skipped", "raw": {"error": "no recipient"}}
    reply_body = (reply_body or "").strip()
    if not reply_body:
        return {"status": "skipped", "raw": {"error": "empty reply"}}

    kind = msg.subject or "your enquiry"
    store_name = store.name if store else et.BRAND
    first = msg.name.split(" ")[0] if msg.name else "there"
    ctx = {
        "store": store_name,
        "subject": kind,
        "message": reply_body,
        "reply": reply_body,
        "customer_name": first,
    }
    rows = [
        ("Subject", kind),
        ("Your message", msg.message or ""),
        ("Our reply", reply_body),
    ]
    subj = "Re: %s | %s" % (kind, et.BRAND)
    subj, plain, html = et.render(
        "contact_reply", ctx, rows=rows, cta_href=_abs("/contact"),
    )
    return send(msg.email, subj, plain, event="contact_reply", store=store, html=html)


def welcome(user, points=100):
    ctx = {"customer_name": user.full_name, "points": points, "store": et.BRAND}
    rows = [("Name", user.full_name), ("Email", user.email)]
    subj, plain, html = et.render("welcome", ctx, rows=rows, cta_href=_abs("/menu"))
    send(user.email, subj, plain, event="welcome", html=html)


def password_reset(user, link):
    ctx = {"customer_name": user.full_name, "link": link}
    subj, plain, html = et.render("password_reset", ctx, cta_href=link)
    send(user.email, subj, plain, event="password_reset", html=html)


def password_changed(user):
    ctx = {"customer_name": user.full_name}
    subj, plain, html = et.render("password_changed", ctx, cta_href=_abs("/login"))
    send(user.email, subj, plain, event="password_changed", html=html)


def staff_removed(email, name, role, store_name, store=None):
    if not email:
        return {"status": "skipped", "raw": {"error": "no recipient"}}
    ctx = {
        "customer_name": name or "there",
        "role": role.replace("_", " ").title(),
        "store": store_name,
    }
    rows = [("Name", name or email), ("Role", ctx["role"]), ("Location", store_name)]
    subj, plain, html = et.render("staff_removed", ctx, rows=rows, cta_href=_abs("/contact"))
    return send(email, subj, plain, event="staff_removed", store=store, html=html)


def staff_invited(user, role, store_name, store=None, temp_password=""):
    if not user.email:
        return {"status": "skipped", "raw": {"error": "no recipient"}}
    ctx = {
        "customer_name": user.full_name or "there",
        "role": role.replace("_", " ").title(),
        "store": store_name,
        "email": user.email,
        "temp_password": temp_password or "(set by your manager)",
    }
    rows = [
        ("Name", user.full_name or user.email),
        ("Role", ctx["role"]),
        ("Location", store_name),
        ("Email", user.email),
        ("Temporary password", ctx["temp_password"]),
    ]
    subj, plain, html = et.render("staff_invited", ctx, rows=rows, cta_href=_abs("/login"))
    return send(user.email, subj, plain, event="staff_invited", store=store, html=html)


def driver_removed(email, name, store_name, store=None):
    if not email:
        return {"status": "skipped", "raw": {"error": "no recipient"}}
    ctx = {"customer_name": name or "there", "store": store_name}
    rows = [("Name", name or email), ("Location", store_name)]
    subj, plain, html = et.render("driver_removed", ctx, rows=rows, cta_href=_abs("/contact"))
    return send(email, subj, plain, event="driver_removed", store=store, html=html)


def unsubscribe_link(email):
    from itsdangerous import URLSafeSerializer
    from flask import current_app
    token = URLSafeSerializer(current_app.config["SECRET_KEY"],
                              salt="ok-unsubscribe").dumps(email)
    return _abs("/unsubscribe/" + token)


def subscribed(email, store=None):
    link = unsubscribe_link(email)
    store = store or sending_store()
    store_name = store.name if store else et.BRAND
    ctx = {"link": link, "store": store_name}
    subj, plain, html = et.render("subscribed", ctx, cta_href=_abs("/deals"))
    send(email, subj, plain, event="subscribed", html=html,
         headers={"List-Unsubscribe": "<%s>" % link,
                  "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})


def gift_card_issued(gc):
    ctx = {"sender_name": gc.sender_name or "Someone",
           "gift_code": gc.code, "gift_value": "$%.2f" % float(gc.balance),
           "message": gc.message or ""}
    rows = [("Code", gc.code), ("Value", ctx["gift_value"]),
            ("From", gc.sender_name), ("Message", gc.message)]
    to = gc.recipient_email or ""
    if to:
        subj, plain, html = et.render("gift_card", ctx, rows=rows, cta_href=_abs("/menu"))
        send(to, subj, plain, event="giftcard_issued", html=html)
    return to


def send_test(to, store=None):
    """Admin SMTP connectivity check, uses the HTML email template."""
    store = sending_store(store)
    if not smtp_gateway.is_enabled(store):
        return {"status": "failed", "raw": {"error": "Enable SMTP and save host + from email first."}}
    cfg = smtp_gateway.store_smtp_config(store)
    loc = store.name if store else et.BRAND
    rows = [
        ("Location", loc),
        ("SMTP host", cfg.get("smtp_host") or "n/a"),
        ("From", cfg.get("from_email") or "n/a"),
    ]
    ctx = {"store": loc}
    subj, plain, html = et.render("smtp_test", ctx, rows=rows)
    return send(to, subj, plain, event="smtp_test", store=store, html=html)
