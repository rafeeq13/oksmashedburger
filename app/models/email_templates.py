"""Customer email copy + layout | stored in SiteSetting, edited in admin.

Keys: email_{template_key}_{field}  e.g. email_welcome_subject
Layout: email_layout_{field}  e.g. email_layout_footer_line1
Placeholders: {brand} {store} {order_number} {customer_name} {link}
{points} {sender_name} {gift_code} {gift_value} {subject} {message}
"""
import re
from markupsafe import escape

from app.models.site import SiteSetting

BRAND = "OK Smashed Burger"

# Global email chrome | the Design tab in admin
# (field, label, default, kind, hint)
_EMAIL_IMAGE_SLOTS = [
    ("img_%02d" % i, "Email image %d" % i, "", "image",
     "Use in HTML as {img_%02d} — logos, banners, icons, SVG/PNG/JPG." % i)
    for i in range(1, 16)
]

EMAIL_LAYOUT = [
    ("header_logo", "Header logo", "/static/img/logo.svg", "image",
     "Shown on the dark bar at the top. SVG or PNG, ~280×56 px."),
    ("footer_logo", "Footer logo", "/static/img/logo.svg", "image",
     "Small logo above the footer text. ~120×40 px."),
] + _EMAIL_IMAGE_SLOTS + [
    ("default_cta_label", "Default CTA label", "Order now", "text",
     "Fallback button text when a template leaves CTA blank."),
    ("default_cta_url", "Default CTA link", "/menu", "text",
     "Fallback button URL — e.g. /menu, /deals, or full https://…"),
    ("footer_line1", "Footer line 1", "{brand} · Philadelphia, PA", "text", ""),
    ("footer_line2", "Footer line 2",
     "Questions? Reply to this email or visit our website.", "area", ""),
    ("footer_legal", "Legal / fine print",
     "You received this email because you interacted with {brand}. "
     "Unsubscribe links appear in marketing messages.", "area", ""),
]

# Appended to every template in admin — full HTML design (required for sending).
HTML_BODY_FIELD = (
    "html_body", "HTML email design", "", "html",
    "Paste your complete HTML email. Use placeholders like {customer_name}, {order_number}, "
    "{message}, {link}, {details_table}, {cta_button}, {header_logo}, {footer_line1}.",
)

# Legacy copy used only when no HTML design is saved yet (auto-layout fallback).
LEGACY_TEMPLATE_COPY = {
    "order_placed": {"title": "Thanks for your order", "body": "Thanks for ordering from {store}! Order {order_number} has been received and is awaiting confirmation.", "footer_note": "Your itemised receipt is attached to this email.", "cta": "Track your order"},
    "order_confirmed": {"title": "You're confirmed", "body": "Your order {order_number} at {store} is confirmed and heading to the kitchen.", "footer_note": "Your itemised receipt is attached to this email.", "cta": "View order"},
    "order_preparing": {"title": "On the grill", "body": "Good news — order {order_number} is on the grill at {store}.", "footer_note": "", "cta": "View order"},
    "order_ready": {"title": "Ready when you are", "body": "Order {order_number} is ready at {store}.", "footer_note": "", "cta": "Get directions"},
    "order_out_for_delivery": {"title": "On the way", "body": "Your order {order_number} from {store} is out for delivery.", "footer_note": "Track it any time from your account.", "cta": "Track order"},
    "order_completed": {"title": "Enjoy!", "body": "Order {order_number} from {store} is complete. Thanks for choosing {brand}!", "footer_note": "Your itemised receipt is attached to this email.", "cta": "Order again"},
    "order_cancelled": {"title": "Order cancelled", "body": "Your order {order_number} at {store} has been cancelled.", "footer_note": "Your receipt is attached. Reply or call us with any questions.", "cta": "Contact us"},
    "welcome": {"title": "Welcome to OK Rewards", "body": "Your account is live and {points} bonus points are already on it. Every order earns more.", "footer_note": "Track your points any time from your account page.", "cta": "Start an order"},
    "password_reset": {"title": "Reset your password", "body": "We got a request to reset the password on your account. This link works once and expires in 60 minutes.", "footer_note": "If this wasn't you, ignore this email — nothing has changed.", "cta": "Reset your password"},
    "password_changed": {"title": "Password updated", "body": "The password on your account was just changed.", "footer_note": "If this wasn't you, contact us immediately.", "cta": "Sign in"},
    "contact_ack": {"title": "Thanks, we've got it", "body": "We have your message and will reply within one business day.", "footer_note": "", "cta": "Browse the menu"},
    "contact_new": {"title": "New website enquiry", "body": "Someone just submitted the contact form.", "footer_note": "Reply straight to the sender's email.", "cta": ""},
    "subscribed": {"title": "You're on the list", "body": "Thanks for subscribing to <b>{store}</b>! Deals, new drops and rewards news land in your inbox first.", "footer_note": '<a href="{link}">Unsubscribe</a> any time.', "cta": "See this week's deals"},
    "gift_card": {"title": "You've been sent a gift card", "body": "Use the code at checkout, online or in store. It never expires.", "footer_note": "", "cta": "Spend it"},
    "newsletter": {"title": "What's new", "body": "{message}", "footer_note": 'You are receiving this because you subscribed. <a href="{link}">Unsubscribe</a>.', "cta": "Order now"},
    "smtp_test": {"title": "SMTP test successful", "body": "This is a test message from your store's SMTP integration. If you received this, email delivery is working.", "footer_note": "Sent from Admin → Integrations → SMTP email.", "cta": ""},
}


def default_html_starter(tpl_key):
    """Attractive branded starter — admins customize in Email templates."""
    legacy = LEGACY_TEMPLATE_COPY.get(tpl_key, {})
    title = legacy.get("title", "{title}")
    body = legacy.get("body", "{body}")
    footer = legacy.get("footer_note", "")
    return (
        '<div style="margin:0;padding:0;background:#f0efeb">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="background:#f0efeb;padding:28px 12px;font-family:Helvetica,Arial,sans-serif;color:#141414">'
        '<tr><td align="center">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="max-width:600px;background:#ffffff;border-radius:18px;overflow:hidden;'
        'box-shadow:0 12px 40px rgba(20,20,20,.10)">'
        # header
        '<tr><td style="background:linear-gradient(135deg,#141414 0%,#2a2a2a 100%);padding:22px 28px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        '<td style="vertical-align:middle">'
        '<img src="{header_logo}" alt="{brand}" width="160" style="display:block;max-width:160px;height:auto;border:0">'
        '</td><td align="right" style="vertical-align:middle;font-size:11px;font-weight:700;'
        'letter-spacing:.12em;text-transform:uppercase;color:#FFC72C">{store}</td>'
        '</tr></table></td></tr>'
        # optional hero
        '<tr><td style="padding:0;line-height:0">{hero_image}</td></tr>'
        # body
        '<tr><td style="padding:32px 28px 24px">'
        '<p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:.14em;'
        'text-transform:uppercase;color:#FFC72C">{brand}</p>'
        '<h1 style="margin:0 0 18px;font-size:26px;line-height:1.2;font-weight:800;color:#141414">'
        + title + '</h1>'
        '<div style="font-size:15px;line-height:1.7;color:#3d3d3d;margin-bottom:22px">' + body + '</div>'
        '{details_table}'
        '{cta_button}'
        + ('<div style="margin-top:20px;padding:14px 16px;background:#faf9f7;border-left:4px solid #FFC72C;'
           'border-radius:0 10px 10px 0;font-size:13px;line-height:1.6;color:#6b6b6b">' + footer + '</div>'
           if footer else '') +
        '</td></tr>'
        # footer
        '<tr><td style="background:#141414;padding:24px 28px;text-align:center">'
        '<img src="{footer_logo}" alt="" width="88" style="display:block;margin:0 auto 12px;border:0;opacity:.95">'
        '<div style="font-size:13px;font-weight:700;color:#FFC72C;margin-bottom:6px">{footer_line1}</div>'
        '<div style="font-size:12px;line-height:1.55;color:#c8c8c8;margin-bottom:10px">{footer_line2}</div>'
        '<div style="font-size:11px;line-height:1.5;color:#8a8a8a;padding-top:12px;border-top:1px solid #2a2a2a">'
        '{footer_legal}</div>'
        '</td></tr>'
        '</table></td></tr></table></div>'
    )


def templates_for_admin():
    """Admin UI: subject, images, CTA + HTML design."""
    out = []
    admin_field_names = ("subject", "hero_image", "cta_label", "cta_url", "html_body")
    for grp_key, grp_label, grp_icon, templates in EMAIL_TEMPLATE_GROUPS:
        tpls = []
        for tpl_key, tpl_label, fields in templates:
            admin_fields = [f for f in fields if f[0] in admin_field_names]
            tpls.append((tpl_key, tpl_label, admin_fields))
        out.append((grp_key, grp_label, grp_icon, tpls))
    return out


# Placeholders available inside HTML designs
EMAIL_PLACEHOLDERS = (
    "{brand}", "{store}", "{order_number}", "{customer_name}", "{points}", "{link}",
    "{sender_name}", "{gift_code}", "{gift_value}", "{subject}", "{message}",
    "{title}", "{body}", "{footer_note}", "{hero_image_url}", "{hero_image}",
    "{cta_url}", "{cta_label}", "{cta_button}", "{details_table}",
    "{header_logo}", "{footer_logo}", "{footer_line1}", "{footer_line2}", "{footer_legal}",
) + tuple("{%s}" % ("img_%02d" % i) for i in range(1, 16))


def _tpl(tpl_key, tpl_label, subject_default):
    legacy = LEGACY_TEMPLATE_COPY.get(tpl_key, {})
    return (tpl_key, tpl_label, [
        ("subject", "Subject line", subject_default, "text"),
        ("hero_image", "Hero banner (optional)", "", "image",
         "Wide image below the header — use {hero_image} in HTML or leave blank."),
        ("cta_label", "CTA button text", legacy.get("cta", ""), "text",
         "Button label — leave blank to hide."),
        ("cta_url", "CTA button link", "", "text",
         "e.g. /menu, /deals, /tracking — or full https:// URL."),
        ("html_body", "HTML email design", default_html_starter(tpl_key), "html", HTML_BODY_FIELD[4]),
    ])


# (group_key, group_label, icon, [(tpl_key, tpl_label, fields), ...])
EMAIL_TEMPLATE_GROUPS = [
    ("orders", "Order updates", "receipt", [
        _tpl("order_placed", "Order received", "We received order {order_number}"),
        _tpl("order_confirmed", "Order confirmed", "Order {order_number} is confirmed"),
        _tpl("order_preparing", "Being prepared", "Order {order_number} is being prepared"),
        _tpl("order_ready", "Ready for pickup", "Order {order_number} is ready"),
        _tpl("order_out_for_delivery", "Out for delivery", "Order {order_number} is on the way"),
        _tpl("order_completed", "Completed", "Order {order_number} complete"),
        _tpl("order_cancelled", "Cancelled", "Order {order_number} cancelled"),
    ]),
    ("account", "Account & auth", "user-lock", [
        _tpl("welcome", "Welcome / sign-up", "Welcome to OK Rewards"),
        _tpl("password_reset", "Password reset", "Reset your password"),
        _tpl("password_changed", "Password changed", "Your password was changed"),
    ]),
    ("marketing", "Contact & marketing", "bullhorn", [
        _tpl("contact_new", "Contact form — staff alert", "[{brand}] New enquiry from {customer_name}"),
        _tpl("contact_ack", "Contact form — customer receipt", "We got your message, {customer_name}"),
        _tpl("subscribed", "Newsletter welcome", "You're on the list"),
        _tpl("gift_card", "Gift card to recipient", "{sender_name} sent you a {brand} gift card"),
        _tpl("newsletter", "Newsletter blast", "News from {brand}"),
        _tpl("smtp_test", "SMTP test", "SMTP test — {brand}"),
    ]),
]


def email_layout_defaults(brand=None):
    brand = brand or BRAND
    out = {}
    for field, _label, default, _kind, _hint in EMAIL_LAYOUT:
        out["email_layout_%s" % field] = default.replace("{brand}", brand)
    return out


def email_template_defaults(brand=None):
    brand = brand or BRAND
    out = {}
    for _grp, _label, _icon, templates in EMAIL_TEMPLATE_GROUPS:
        for tpl_key, _tpl_label, fields in templates:
            for field, _fl, default, *_rest in fields:
                key = "email_%s_%s" % (tpl_key, field)
                out[key] = default.replace("{brand}", brand) if field == "subject" else default
    return out


def all_email_setting_keys():
    keys = set(email_layout_defaults())
    keys.update(email_template_defaults())
    return keys


def email_image_keys():
    keys = {k for k in email_layout_defaults()
            if k.startswith("email_layout_") and any(
                f[0] == k.replace("email_layout_", "") and f[3] == "image" for f in EMAIL_LAYOUT)}
    for _g, _l, _i, templates in EMAIL_TEMPLATE_GROUPS:
        for tpl_key, _tl, fields in templates:
            for field, _fl, _def, kind, *_rest in fields:
                if kind == "image":
                    keys.add("email_%s_%s" % (tpl_key, field))
    return keys


def group_for_template(tpl_key):
    for grp_key, grp_label, _icon, templates in EMAIL_TEMPLATE_GROUPS:
        for key, _tl, _fields in templates:
            if key == tpl_key:
                return grp_key, grp_label
    return None, None


def _setting_key(tpl_key, field):
    return "email_%s_%s" % (tpl_key, field)


def _layout_key(field):
    return "email_layout_%s" % field


def _raw_setting(key):
    row = SiteSetting.query.filter_by(key=key).first()
    return row.value if row and row.value else None


def get_layout(field, brand=None):
    defaults = email_layout_defaults(brand)
    key = _layout_key(field)
    return _raw_setting(key) or defaults.get(key, "")


def get_field(tpl_key, field, brand=None):
    """Saved value or built-in default."""
    defaults = email_template_defaults(brand)
    key = _setting_key(tpl_key, field)
    val = _raw_setting(key)
    if not val and field == "html_body":
        val = _raw_setting(_setting_key(tpl_key, "custom_html"))
    if val:
        return val
    if field in ("title", "body", "footer_note", "cta"):
        legacy = LEGACY_TEMPLATE_COPY.get(tpl_key, {})
        if field in legacy:
            return legacy[field]
    if field == "footer_note":
        legacy = _raw_setting(_setting_key(tpl_key, "outro"))
        if legacy:
            return legacy
    return defaults.get(key, "")


def format_text(template, ctx):
    if not template:
        return ""
    safe = {k: ("" if v is None else v) for k, v in ctx.items()}
    try:
        return template.format(**safe)
    except (KeyError, ValueError):
        return template


def abs_media(url):
    """Turn a site-relative upload path into an absolute URL for email clients."""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/static/"):
        try:
            from flask import url_for
            return url_for("static", filename=url[len("/static/"):], _external=True)
        except Exception:
            pass
    if url.startswith("/"):
        try:
            from flask import url_for
            return url_for("website.home", _external=True).rstrip("/") + url
        except Exception:
            return "https://oksmashedburger.com" + url
    return url


def _esc(text):
    return str(escape(text)).replace("\n", "<br>")


def _url_attr(url):
    """Safe for HTML attribute values | do not HTML-escape whole URLs for img src."""
    return str(url or "").replace('"', "&quot;")


def html_shell(title, intro, rows=None, cta=None, footer_note=None, brand=None,
               hero_image=None, layout=None):
    brand = brand or BRAND
    layout = layout or {}
    header_logo = abs_media(layout.get("header_logo") or get_layout("header_logo", brand))
    footer_logo = abs_media(layout.get("footer_logo") or get_layout("footer_logo", brand))
    footer_line1 = layout.get("footer_line1") or get_layout("footer_line1", brand)
    footer_line2 = layout.get("footer_line2") or get_layout("footer_line2", brand)
    footer_legal = layout.get("footer_legal") or get_layout("footer_legal", brand)
    hero = abs_media(hero_image or "")

    parts = [
        '<div style="background:#f0efeb;padding:32px 14px;font-family:Helvetica,Arial,sans-serif;color:#141414">',
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;'
        'box-shadow:0 8px 28px rgba(20,20,20,.08)">',
        '<tr><td style="background:#141414;padding:20px 28px;text-align:left">',
    ]
    if header_logo:
        parts.append('<img src="%s" alt="%s" width="168" style="display:block;max-width:168px;height:auto;border:0">'
                     % (_url_attr(header_logo), _esc(brand)))
    else:
        parts.append('<span style="color:#FFC72C;font-size:20px;font-weight:800;letter-spacing:.03em">%s</span>'
                     % _esc(brand))
    parts.append('</td></tr>')

    if hero:
        parts.append(
            '<tr><td style="padding:0;line-height:0">'
            '<img src="%s" alt="" width="600" style="display:block;width:100%%;max-width:600px;height:auto;border:0">'
            '</td></tr>' % _url_attr(hero))

    parts += [
        '<tr><td style="padding:28px 28px 8px">',
        '<h1 style="margin:0 0 16px;font-size:24px;line-height:1.25;font-weight:800;color:#141414">%s</h1>' % _esc(title),
        '<div style="background:#faf9f7;border-left:4px solid #FFC72C;border-radius:0 10px 10px 0;'
        'padding:16px 18px;margin:0 0 20px">',
        '<p style="margin:0;font-size:15px;line-height:1.65;color:#3d3d3d">%s</p></div>' % _esc(intro),
    ]

    if rows:
        parts.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
            'style="font-size:14px;border:1px solid #eceae4;border-radius:10px;overflow:hidden;margin:0 0 20px">')
        first = True
        for label, value in rows:
            if value in (None, ""):
                continue
            bg = "#ffffff" if first else "#faf9f7"
            first = False
            parts.append(
                '<tr style="background:%s">'
                '<td style="padding:11px 14px;color:#6b6b6b;width:38%%;vertical-align:top;border-top:1px solid #eceae4">%s</td>'
                '<td style="padding:11px 14px;font-weight:600;vertical-align:top;border-top:1px solid #eceae4">%s</td>'
                '</tr>' % (bg, _esc(label), _esc(value)))
        parts.append('</table>')

    if cta and cta[0] and cta[1]:
        parts.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 8px">'
            '<tr><td style="border-radius:10px;background:#FFC72C">'
            '<a href="%s" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:800;'
            'color:#141414;text-decoration:none">%s</a></td></tr></table>' % (_url_attr(cta[1]), _esc(cta[0])))

    if footer_note:
        parts.append(
            '<div style="margin:18px 0 0;padding:14px 16px;background:#f6f5f2;border-radius:10px;'
            'font-size:13px;line-height:1.6;color:#6b6b6b">%s</div>' % _esc(footer_note))

    parts.append('</td></tr>')

    parts.append('<tr><td style="padding:22px 28px 26px;background:#141414;text-align:center">')
    if footer_logo:
        parts.append('<img src="%s" alt="%s" width="96" style="display:block;margin:0 auto 12px;'
                       'max-width:96px;height:auto;border:0;opacity:.95">' % (_url_attr(footer_logo), _esc(brand)))
    if footer_line1:
        parts.append('<p style="margin:0 0 8px;font-size:13px;font-weight:700;color:#FFC72C">%s</p>'
                     % _esc(footer_line1))
    if footer_line2:
        parts.append('<p style="margin:0 0 12px;font-size:12px;line-height:1.55;color:#c8c8c8">%s</p>'
                     % _esc(footer_line2))
    if footer_legal:
        parts.append('<p style="margin:0;padding-top:12px;border-top:1px solid #2a2a2a;font-size:11px;'
                     'line-height:1.5;color:#8a8a8a">%s</p>' % _esc(footer_legal))
    parts.append('</td></tr></table></div>')
    return "".join(parts)


def plain_text(intro, rows=None, cta=None, footer_note=None, brand=None):
    brand = brand or BRAND
    parts = [intro, ""]
    for label, value in (rows or []):
        if value not in (None, ""):
            parts.append("%s: %s" % (label, value))
    if rows:
        parts.append("")
    if cta and cta[0] and cta[1]:
        parts += [cta[0] + ": " + cta[1], ""]
    if footer_note:
        parts.append(footer_note)
    parts += ["", "| " + brand]
    return "\n".join(parts)


def _rows_html(rows):
    if not rows:
        return ""
    parts = [
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="font-size:14px;border:1px solid #eceae4;border-radius:10px;overflow:hidden;margin:0 0 20px">']
    first = True
    for label, value in rows:
        if value in (None, ""):
            continue
        bg = "#ffffff" if first else "#faf9f7"
        first = False
        parts.append(
            '<tr style="background:%s">'
            '<td style="padding:11px 14px;color:#6b6b6b;width:38%%;vertical-align:top;'
            'border-top:1px solid #eceae4">%s</td>'
            '<td style="padding:11px 14px;font-weight:600;vertical-align:top;'
            'border-top:1px solid #eceae4">%s</td></tr>' % (bg, _esc(label), _esc(value)))
    parts.append("</table>")
    return "".join(parts)


def _cta_button_html(cta):
    if not cta or not cta[0] or not cta[1]:
        return ""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 8px">'
        '<tr><td style="border-radius:10px;background:#FFC72C">'
        '<a href="%s" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:800;'
        'color:#141414;text-decoration:none">%s</a></td></tr></table>'
        % (_url_attr(cta[1]), _esc(cta[0])))


def _hero_image_html(url):
    url = abs_media(url or "")
    if not url:
        return ""
    return (
        '<img src="%s" alt="" width="600" '
        'style="display:block;width:100%%;max-width:600px;height:auto;border:0">'
        % _url_attr(url))


def merge_render_context(tpl_key, ctx, title, body, footer_note, hero_image, rows, cta, brand):
    """All placeholders available in custom HTML templates."""
    brand = brand or BRAND
    hero_url = abs_media(hero_image or "")
    merged = dict(ctx, brand=brand, title=title, body=body, footer_note=footer_note or "",
                  hero_image_url=hero_url, hero_image=_hero_image_html(hero_image),
                  header_logo=abs_media(get_layout("header_logo", brand)),
                  footer_logo=abs_media(get_layout("footer_logo", brand)),
                  footer_line1=format_text(get_layout("footer_line1", brand), dict(ctx, brand=brand)),
                  footer_line2=format_text(get_layout("footer_line2", brand), dict(ctx, brand=brand)),
                  footer_legal=format_text(get_layout("footer_legal", brand), dict(ctx, brand=brand)),
                  details_table=_rows_html(rows),
                  cta_button=_cta_button_html(cta))
    for i in range(1, 16):
        key = "img_%02d" % i
        merged[key] = abs_media(get_layout(key, brand))
    if cta and cta[0] and cta[1]:
        merged["cta_label"] = cta[0]
        merged["cta_url"] = cta[1]
        merged["link"] = ctx.get("link") or cta[1]
    else:
        merged.setdefault("cta_label", "")
        merged.setdefault("cta_url", "")
        merged.setdefault("link", ctx.get("link") or "")
    return merged


def html_to_plain(html):
    """Rough plain-text version for multipart email clients."""
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</tr>", "\n", text)
    text = re.sub(r"(?i)</h[1-6]>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render(tpl_key, ctx, rows=None, cta_href=None, brand=None):
    """Return (subject, plain_body, html_body) — always from the HTML template design."""
    brand = brand or ctx.get("brand") or BRAND
    ctx = dict(ctx, brand=brand)
    subject = format_text(get_field(tpl_key, "subject", brand), ctx)
    title = format_text(get_field(tpl_key, "title", brand), ctx)
    body = format_text(get_field(tpl_key, "body", brand), ctx)
    footer_note = format_text(get_field(tpl_key, "footer_note", brand), ctx)
    hero_image = get_field(tpl_key, "hero_image", brand)
    cta_label = format_text(
        get_field(tpl_key, "cta_label", brand) or get_field(tpl_key, "cta", brand) or get_layout("default_cta_label", brand),
        ctx)
    cta_url_raw = get_field(tpl_key, "cta_url", brand) or get_layout("default_cta_url", brand) or (cta_href or "")
    cta_url = format_text(cta_url_raw, ctx)
    if cta_url and cta_url.startswith("/"):
        try:
            from flask import url_for
            cta_url = url_for("website.home", _external=True).rstrip("/") + cta_url
        except Exception:
            cta_url = "https://oksmashedburger.com" + cta_url
    cta = (cta_label.strip(), cta_url.strip()) if cta_label and cta_url else None
    html_raw = (get_field(tpl_key, "html_body", brand) or "").strip()
    if not html_raw:
        html_raw = default_html_starter(tpl_key)
    rich = merge_render_context(tpl_key, ctx, title, body, footer_note, hero_image, rows, cta, brand)
    html = format_text(html_raw, rich)
    plain = html_to_plain(html) or plain_text(body, rows=rows, cta=cta, footer_note=footer_note or None, brand=brand)
    return subject, plain, html


def preview_context(tpl_key):
    """Sample merge data for the admin live preview."""
    base = {"brand": BRAND, "store": "Center City", "customer_name": "Alex",
            "order_number": "OK-4012", "points": "100", "sender_name": "Jordan",
            "gift_code": "GIFT-OK-1234", "gift_value": "$25.00",
            "subject": "Catering enquiry", "message": "Looking to cater an office lunch."}
    if tpl_key.startswith("order_"):
        return base
    if tpl_key == "gift_card":
        return base
    if tpl_key == "contact_ack" or tpl_key == "contact_new":
        return base
    if tpl_key == "newsletter":
        return dict(base, message="<p>Looking to cater an office lunch for 20 people.</p>")
    return {k: v for k, v in base.items() if k not in ("order_number",)}


def preview_rows(tpl_key):
    if tpl_key.startswith("order_"):
        return [
            ("Order number", "OK-4012"),
            ("Store", "Center City"),
            ("Type", "Delivery"),
            ("1× Classic Smash", "$12.99 — Double · + Bacon"),
            ("Subtotal", "$12.99"),
            ("Tax", "$1.04"),
            ("Delivery", "$2.99"),
            ("Tip", "$3.00"),
            ("Total", "$20.02"),
        ]
    if tpl_key == "welcome":
        return [("Name", "Alex Morgan"), ("Email", "alex@example.com")]
    if tpl_key == "gift_card":
        return [("Code", "GIFT-OK-1234"), ("Value", "$25.00"), ("From", "Jordan")]
    if tpl_key == "contact_ack":
        return [("Subject", "Catering enquiry"), ("What you sent", "Office lunch for 20 people.")]
    if tpl_key == "contact_new":
        return [("From", "Alex Morgan"), ("Email", "alex@example.com"), ("Message", "Office lunch for 20.")]
    return None


def _has_field(tpl_key, field):
    if field in ("html_body", "custom_html"):
        return True
    for _g, _l, _i, templates in EMAIL_TEMPLATE_GROUPS:
        for key, _tl, fields in templates:
            if key == tpl_key:
                return any(f[0] == field for f in fields)
    return False


ORDER_EVENT_KEYS = {
    "placed": "order_placed",
    "confirmed": "order_confirmed",
    "preparing": "order_preparing",
    "ready": "order_ready",
    "out_for_delivery": "order_out_for_delivery",
    "completed": "order_completed",
    "cancelled": "order_cancelled",
}
