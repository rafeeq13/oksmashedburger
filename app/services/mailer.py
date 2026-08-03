"""Site-level email.

`notifications.py` covers order status mail, which is always tied to one order
and one store. Everything else the site sends — contact replies, the welcome
mail, password resets, newsletter, gift cards — has no order behind it, so it
goes through here instead.

Delivery still runs on a STORE's SendGrid account (that is how this platform is
set up: each location holds its own keys), so we pick a sending store: the one
the visitor is browsing if there is one, otherwise the first location with
SendGrid switched on. Every send is written to the notifications log with
order_id=NULL, so the admin sees site mail and order mail in one place.

In demo mode (DEMO_PAYMENTS unset or "true") sends are simulated, logged and
nothing leaves the building — the flows stay testable without real keys.
"""
from flask import url_for

from app.extensions import db
from app.integrations import sendgrid_gateway
from app.models.notification import Notification
from app.models.store import Store

BRAND = "OK Smashed Burger"


# ── plumbing ────────────────────────────────────────────────────────────────

def sending_store(preferred=None):
    """The store whose SendGrid account carries this message."""
    if preferred is not None and sendgrid_gateway.is_enabled(preferred):
        return preferred
    try:
        from app.helpers import get_current_store
        current = get_current_store()
        if current is not None and sendgrid_gateway.is_enabled(current):
            return current
    except Exception:
        pass  # no request context (CLI, worker) — fall through to any store
    for s in Store.query.filter_by(is_active=True).order_by(Store.id).all():
        if sendgrid_gateway.is_enabled(s):
            return s
    return preferred or Store.query.order_by(Store.id).first()


def business_inbox(store=None):
    """Where enquiries land. The store's own address wins; the SendGrid sender
    is the fallback so a submission is never dropped for want of a recipient."""
    store = store or sending_store()
    if store and store.email:
        return store.email
    cfg = sendgrid_gateway.store_sendgrid_config(store)
    return cfg.get("from_email") or ""


def send(to, subject, body, event, store=None, attachment=None, html=None, headers=None):
    """Send one site email and log it. Returns the gateway result dict."""
    if not to:
        return {"status": "skipped", "raw": {"error": "no recipient"}}
    store = sending_store(store)
    res = sendgrid_gateway.send_email(store, to, subject, body,
                                      attachment=attachment, html=html, headers=headers)
    db.session.add(Notification(
        order_id=None, store_id=store.id if store else None,
        channel="email", provider="sendgrid", recipient=to,
        subject=subject[:160], body=body, event=event[:30],
        status=res.get("status", "simulated"),
        provider_ref="site_%s_%s" % (event, to)))
    db.session.commit()
    print("[mail] %s -> %s (%s)" % (event, to, res.get("status")))
    return res


def _abs(path):
    """Absolute URL for links inside an email, with a sane fallback when the
    mail is generated outside a request (CLI, background job)."""
    try:
        return url_for("website.home", _external=True).rstrip("/") + path
    except Exception:
        return "https://oksmashedburger.com" + path


# ── shared HTML shell ───────────────────────────────────────────────────────

def _html(title, intro, rows=None, cta=None, outro=None):
    """One branded shell for every message. Inline styles only, tables for
    layout — that is what survives Gmail, Outlook and Apple Mail."""
    body = ['<div style="background:#f6f5f2;padding:28px 12px;font-family:'
            'Helvetica,Arial,sans-serif;color:#141414">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            # %% — this string is %-formatted below, so a literal percent must be doubled
            'width="100%%" style="max-width:560px;margin:0 auto;background:#fff;'
            'border-radius:14px;overflow:hidden">'
            '<tr><td style="background:#141414;padding:22px 26px">'
            '<span style="color:#FFC72C;font-size:19px;font-weight:800;'
            'letter-spacing:.02em">%s</span></td></tr>'
            '<tr><td style="padding:26px">'
            '<h1 style="margin:0 0 12px;font-size:21px;line-height:1.25">%s</h1>'
            '<p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#3d3d3d">%s</p>'
            % (BRAND, title, intro)]

    if rows:
        body.append('<table role="presentation" cellpadding="0" cellspacing="0" '
                    'border="0" width="100%" style="font-size:14px;'
                    'border-top:1px solid #ececec">')
        for label, value in rows:
            if value in (None, ""):
                continue
            body.append(
                '<tr>'
                '<td style="padding:9px 0;color:#6b6b6b;white-space:nowrap;'
                'vertical-align:top;width:38%%">%s</td>'
                '<td style="padding:9px 0;font-weight:600;vertical-align:top">%s</td>'
                '</tr>' % (label, str(value).replace("\n", "<br>")))
        body.append('</table>')

    if cta:
        label, href = cta
        body.append('<p style="margin:24px 0 0"><a href="%s" style="display:inline-block;'
                    'background:#FFC72C;color:#141414;text-decoration:none;font-weight:700;'
                    'padding:13px 26px;border-radius:8px;font-size:15px">%s</a></p>' % (href, label))

    if outro:
        body.append('<p style="margin:22px 0 0;font-size:13px;line-height:1.6;'
                    'color:#6b6b6b">%s</p>' % outro)

    body.append('</td></tr><tr><td style="padding:16px 26px;background:#faf9f7;'
                'font-size:12px;color:#8a8a8a">%s · Philadelphia</td></tr>'
                '</table></div>' % BRAND)
    return "".join(body)


def _text(intro, rows=None, cta=None, outro=None):
    """Plain-text twin of the HTML above."""
    parts = [intro, ""]
    for label, value in (rows or []):
        if value not in (None, ""):
            parts.append("%s: %s" % (label, value))
    if rows:
        parts.append("")
    if cta:
        parts += [cta[0] + ": " + cta[1], ""]
    if outro:
        parts.append(outro)
    parts += ["", "— " + BRAND]
    return "\n".join(parts)


# ── the messages ────────────────────────────────────────────────────────────

def contact_received(msg, store=None):
    """Two emails per submission: the enquiry to the business, a receipt to the
    person who sent it. `msg` is the saved ContactMessage."""
    kind = msg.subject or "Enquiry"
    rows = [("From", msg.name or "—"), ("Email", msg.email or "—"),
            ("Order number", msg.order_number), ("Message", msg.message)]

    to_business = business_inbox(store)
    send(to_business, "[%s] %s — %s" % (BRAND, kind, msg.name or msg.email or "website"),
         _text("A new %s came in from the website." % kind.lower(), rows),
         html=_html("New %s" % kind.lower(),
                    "Someone just submitted the form on the website.", rows,
                    outro="Reply straight to %s to answer them." % (msg.email or "the sender")),
         event="contact_new", store=store)

    if msg.email:
        send(msg.email, "We got your message, %s" % (msg.name.split(" ")[0] if msg.name else "thanks"),
             _text("Thanks for getting in touch. We have your message and will reply "
                   "within one business day.",
                   [("Subject", kind), ("What you sent", msg.message)]),
             html=_html("Thanks, we've got it",
                        "We have your message and will reply within one business day.",
                        [("Subject", kind), ("What you sent", msg.message)],
                        cta=("Browse the menu", _abs("/menu"))),
             event="contact_ack", store=store)


def welcome(user, points=100):
    send(user.email, "Welcome to OK Rewards",
         _text("Your account is live and %d bonus points are already on it." % points,
               [("Name", user.full_name), ("Email", user.email),
                ("Starting points", points)],
               cta=("Start an order", _abs("/menu"))),
         html=_html("Welcome to OK Rewards",
                    "Your account is live and <b>%d bonus points</b> are already on it. "
                    "Every order earns more." % points,
                    [("Name", user.full_name), ("Email", user.email)],
                    cta=("Start an order", _abs("/menu")),
                    outro="Track your points any time from your account page."),
         event="welcome")


def password_reset(user, link):
    send(user.email, "Reset your password",
         _text("We got a request to reset the password on your account. "
               "The link below works once and expires in 60 minutes.",
               cta=("Reset your password", link),
               outro="If this wasn't you, ignore this email — nothing has changed."),
         html=_html("Reset your password",
                    "We got a request to reset the password on your account. "
                    "This link works once and expires in 60 minutes.",
                    cta=("Reset your password", link),
                    outro="If this wasn't you, ignore this email — nothing has changed "
                          "and your current password still works."),
         event="password_reset")


def password_changed(user):
    send(user.email, "Your password was changed",
         _text("The password on your account was just changed.",
               outro="If this wasn't you, contact us immediately."),
         html=_html("Your password was changed",
                    "The password on your account was just changed.",
                    cta=("Sign in", _abs("/login")),
                    outro="If this wasn't you, contact us immediately."),
         event="password_changed")


def unsubscribe_link(email):
    """One-click opt-out URL. Signed rather than stored: no token table to keep,
    and the link cannot be guessed or edited to unsubscribe somebody else."""
    from itsdangerous import URLSafeSerializer
    from flask import current_app
    token = URLSafeSerializer(current_app.config["SECRET_KEY"],
                              salt="ok-unsubscribe").dumps(email)
    return _abs("/unsubscribe/" + token)


def subscribed(email):
    """Marketing mail, so it carries a real opt-out. US CAN-SPAM requires a
    working unsubscribe in every commercial message, and List-Unsubscribe is
    what gets Gmail/Outlook to surface their own one-click button — without it
    people hit "spam" instead, which wrecks the sending domain's reputation."""
    link = unsubscribe_link(email)
    send(email, "You're on the list",
         _text("Thanks for subscribing. Deals, new drops and rewards news land here first.",
               cta=("See this week's deals", _abs("/deals")),
               outro="Unsubscribe at any time: " + link),
         html=_html("You're on the list",
                    "Thanks for subscribing. Deals, new drops and rewards news land "
                    "in your inbox first.",
                    cta=("See this week's deals", _abs("/deals")),
                    outro=("Not what you wanted? <a href=\"%s\" style=\"color:#6b6b6b\">"
                           "Unsubscribe in one click</a>." % link)),
         headers={"List-Unsubscribe": "<%s>" % link,
                  "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
         event="subscribed")


def gift_card_issued(gc):
    """To the recipient if one was given, otherwise a receipt to the buyer."""
    rows = [("Code", gc.code), ("Value", "$%.2f" % float(gc.balance)),
            ("From", gc.sender_name), ("Message", gc.message)]
    to = gc.recipient_email or ""
    if to:
        send(to, "%s sent you a %s gift card" % (gc.sender_name or "Someone", BRAND),
             _text("You've been sent a gift card. Use the code at checkout, "
                   "online or in store.", rows, cta=("Spend it", _abs("/menu"))),
             html=_html("You've been sent a gift card",
                        "Use the code at checkout, online or in store. It never expires.",
                        rows, cta=("Spend it", _abs("/menu"))),
             event="giftcard_issued")
    return to
