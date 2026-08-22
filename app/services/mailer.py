"""Site-level email (no order attached) — sent via each store's SMTP.

Order status mail lives in notifications.py. Template copy is editable in
/admin/email-templates; delivery uses /admin/integrations → SMTP.
"""
from flask import url_for

from app.extensions import db
from app.integrations import smtp_gateway
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
    if store and store.email:
        return store.email
    cfg = smtp_gateway.store_smtp_config(store)
    return cfg.get("from_email") or ""


def send(to, subject, body, event, store=None, attachment=None, html=None, headers=None):
    if not to:
        return {"status": "skipped", "raw": {"error": "no recipient"}}
    store = sending_store(store)
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
    try:
        return url_for("website.home", _external=True).rstrip("/") + path
    except Exception:
        return "https://oksmashedburger.com" + path


def contact_received(msg, store=None):
    kind = msg.subject or "Enquiry"
    rows = [("From", msg.name or "—"), ("Email", msg.email or "—"),
            ("Order number", msg.order_number), ("Message", msg.message)]
    ctx = {"store": (store.name if store else et.BRAND), "subject": kind,
           "message": msg.message or ""}

    to_business = business_inbox(store)
    if to_business:
        send(to_business, "[%s] %s — %s" % (et.BRAND, kind, msg.name or msg.email or "website"),
             et.plain_text("A new %s came in from the website." % kind.lower(), rows=rows),
             html=et.html_shell("New %s" % kind.lower(),
                                "Someone just submitted the form on the website.",
                                rows=rows,
                                footer_note="Reply straight to %s to answer them." % (msg.email or "the sender")),
             event="contact_new", store=store)

    if msg.email:
        first = msg.name.split(" ")[0] if msg.name else "there"
        ctx = {"store": (store.name if store else et.BRAND), "subject": kind,
               "message": msg.message or "", "customer_name": first}
        subj, plain, html = et.render("contact_ack", ctx,
                                      rows=[("Subject", kind), ("What you sent", msg.message)],
                                      cta_href=_abs("/menu"))
        send(msg.email, subj, plain, event="contact_ack", store=store, html=html)


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


def unsubscribe_link(email):
    from itsdangerous import URLSafeSerializer
    from flask import current_app
    token = URLSafeSerializer(current_app.config["SECRET_KEY"],
                              salt="ok-unsubscribe").dumps(email)
    return _abs("/unsubscribe/" + token)


def subscribed(email):
    link = unsubscribe_link(email)
    ctx = {}
    subj, plain, html = et.render("subscribed", ctx, cta_href=_abs("/deals"))
    plain += "\n\nUnsubscribe: " + link
    html = html.replace(
        "Unsubscribe any time",
        ('Not what you wanted? <a href="%s" style="color:#6b6b6b">'
         "Unsubscribe in one click</a>." % link))
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
