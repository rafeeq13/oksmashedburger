"""Customer email copy + layout | stored in SiteSetting, edited in admin.

Keys: email_{template_key}_{field}  e.g. email_welcome_subject
Layout: email_layout_{field}  e.g. email_layout_footer_line1
Placeholders: {brand} {store} {order_number} {customer_name} {link}
{points} {sender_name} {gift_code} {gift_value} {subject} {message}
"""
from markupsafe import escape

from app.models.site import SiteSetting

BRAND = "OK Smashed Burger"

# Global email chrome | the Design tab in admin
# (field, label, default, kind, hint)
EMAIL_LAYOUT = [
    ("header_logo", "Header logo", "/static/img/logo.svg", "image",
     "Shown on the dark bar at the top. Square or wide logo, ~280×56 px."),
    ("footer_logo", "Footer logo", "/static/img/logo.svg", "image",
     "Small logo above the footer text. ~120×40 px."),
    ("footer_line1", "Footer line 1", "{brand} · Philadelphia, PA", "text", ""),
    ("footer_line2", "Footer line 2",
     "Questions? Reply to this email or visit our website.", "area", ""),
    ("footer_legal", "Legal / fine print",
     "You received this email because you interacted with {brand}. "
     "Unsubscribe links appear in marketing messages.", "area", ""),
]

# Appended to every template in admin | optional full HTML override
CUSTOM_HTML_FIELD = (
    "custom_html", "Full HTML email (optional)", "", "html",
    "Paste a complete designed HTML email. Leave blank to use the built-in layout "
    "from the fields above. Placeholders below are replaced when sent.",
)

# Placeholders available inside custom_html (and text fields)
EMAIL_PLACEHOLDERS = (
    "{brand}", "{store}", "{order_number}", "{customer_name}", "{points}", "{link}",
    "{sender_name}", "{gift_code}", "{gift_value}", "{subject}", "{message}",
    "{title}", "{body}", "{footer_note}", "{hero_image_url}", "{hero_image}",
    "{cta_url}", "{cta_label}", "{cta_button}", "{details_table}",
    "{header_logo}", "{footer_logo}", "{footer_line1}", "{footer_line2}", "{footer_legal}",
)


def templates_for_admin():
    """Registry copy with the custom HTML field on every template."""
    out = []
    for grp_key, grp_label, grp_icon, templates in EMAIL_TEMPLATE_GROUPS:
        tpls = []
        for tpl_key, tpl_label, fields in templates:
            tpls.append((tpl_key, tpl_label, list(fields) + [CUSTOM_HTML_FIELD]))
        out.append((grp_key, grp_label, grp_icon, tpls))
    return out


# (group_key, group_label, icon, [(tpl_key, tpl_label, fields), ...])
EMAIL_TEMPLATE_GROUPS = [
    ("orders", "Order updates", "receipt", [
        ("order_placed", "Order received", [
            ("subject", "Subject", "We received order {order_number}", "text"),
            ("title", "Heading", "Thanks for your order", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Thanks for ordering from {store}! Order {order_number} has been received and is awaiting confirmation.", "area"),
            ("footer_note", "Note above footer", "Your itemised receipt is attached to this email.", "area"),
        ]),
        ("order_confirmed", "Order confirmed", [
            ("subject", "Subject", "Order {order_number} is confirmed", "text"),
            ("title", "Heading", "You're confirmed", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Your order {order_number} at {store} is confirmed and heading to the kitchen.", "area"),
            ("footer_note", "Note above footer", "Your itemised receipt is attached to this email.", "area"),
        ]),
        ("order_preparing", "Being prepared", [
            ("subject", "Subject", "Order {order_number} is being prepared", "text"),
            ("title", "Heading", "On the grill", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Good news | order {order_number} is on the grill at {store}.", "area"),
            ("footer_note", "Note above footer", "", "area"),
        ]),
        ("order_ready", "Ready for pickup", [
            ("subject", "Subject", "Order {order_number} is ready", "text"),
            ("title", "Heading", "Ready when you are", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Order {order_number} is ready at {store}.", "area"),
            ("footer_note", "Note above footer", "", "area"),
        ]),
        ("order_out_for_delivery", "Out for delivery", [
            ("subject", "Subject", "Order {order_number} is on the way", "text"),
            ("title", "Heading", "On the way", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Your order {order_number} from {store} is out for delivery.", "area"),
            ("footer_note", "Note above footer", "Track it any time from your account.", "area"),
        ]),
        ("order_completed", "Completed", [
            ("subject", "Subject", "Order {order_number} complete", "text"),
            ("title", "Heading", "Enjoy!", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Order {order_number} from {store} is complete. Thanks for choosing {brand}!", "area"),
            ("footer_note", "Note above footer", "", "area"),
        ]),
        ("order_cancelled", "Cancelled", [
            ("subject", "Subject", "Order {order_number} cancelled", "text"),
            ("title", "Heading", "Order cancelled", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Your order {order_number} at {store} has been cancelled.", "area"),
            ("footer_note", "Note above footer", "Reply or call us with any questions.", "area"),
        ]),
    ]),
    ("account", "Account & auth", "user-lock", [
        ("welcome", "Welcome / sign-up", [
            ("subject", "Subject", "Welcome to OK Rewards", "text"),
            ("title", "Heading", "Welcome to OK Rewards", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Your account is live and {points} bonus points are already on it. Every order earns more.", "area"),
            ("cta", "Button label", "Start an order", "text"),
            ("footer_note", "Note above footer", "Track your points any time from your account page.", "area"),
        ]),
        ("password_reset", "Password reset", [
            ("subject", "Subject", "Reset your password", "text"),
            ("title", "Heading", "Reset your password", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "We got a request to reset the password on your account. This link works once and expires in 60 minutes.", "area"),
            ("cta", "Button label", "Reset your password", "text"),
            ("footer_note", "Note above footer", "If this wasn't you, ignore this email | nothing has changed.", "area"),
        ]),
        ("password_changed", "Password changed", [
            ("subject", "Subject", "Your password was changed", "text"),
            ("title", "Heading", "Password updated", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "The password on your account was just changed.", "area"),
            ("cta", "Button label", "Sign in", "text"),
            ("footer_note", "Note above footer", "If this wasn't you, contact us immediately.", "area"),
        ]),
    ]),
    ("marketing", "Contact & marketing", "bullhorn", [
        ("contact_ack", "Contact form | customer receipt", [
            ("subject", "Subject", "We got your message, {customer_name}", "text"),
            ("title", "Heading", "Thanks, we've got it", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "We have your message and will reply within one business day.", "area"),
            ("cta", "Button label", "Browse the menu", "text"),
            ("footer_note", "Note above footer", "", "area"),
        ]),
        ("subscribed", "Newsletter welcome", [
            ("subject", "Subject", "You're on the list", "text"),
            ("title", "Heading", "You're on the list", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Thanks for subscribing. Deals, new drops and rewards news land in your inbox first.", "area"),
            ("cta", "Button label", "See this week's deals", "text"),
            ("footer_note", "Note above footer", "Unsubscribe any time from the link at the bottom of every email.", "area"),
        ]),
        ("gift_card", "Gift card to recipient", [
            ("subject", "Subject", "{sender_name} sent you a {brand} gift card", "text"),
            ("title", "Heading", "You've been sent a gift card", "text"),
            ("hero_image", "Hero banner", "", "image"),
            ("body", "Message", "Use the code at checkout, online or in store. It never expires.", "area"),
            ("cta", "Button label", "Spend it", "text"),
            ("footer_note", "Note above footer", "", "area"),
        ]),
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
            for field, _fl, default, _kind in fields:
                out["email_%s_%s" % (tpl_key, field)] = default.replace("{brand}", brand)
            out["email_%s_custom_html" % tpl_key] = ""
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
            for field, _fl, _def, kind in fields:
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
    """Saved value or built-in default (footer_note falls back to legacy outro)."""
    defaults = email_template_defaults(brand)
    key = _setting_key(tpl_key, field)
    val = _raw_setting(key)
    if val:
        return val
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
    if cta and cta[0] and cta[1]:
        merged["cta_label"] = cta[0]
        merged["cta_url"] = cta[1]
        merged["link"] = ctx.get("link") or cta[1]
    else:
        merged.setdefault("cta_label", "")
        merged.setdefault("cta_url", "")
        merged.setdefault("link", ctx.get("link") or "")
    return merged


def render(tpl_key, ctx, rows=None, cta_href=None, brand=None):
    """Return (subject, plain_body, html_body) for a template key."""
    brand = brand or ctx.get("brand") or BRAND
    ctx = dict(ctx, brand=brand)
    subject = format_text(get_field(tpl_key, "subject", brand), ctx)
    title = format_text(get_field(tpl_key, "title", brand), ctx)
    body = format_text(get_field(tpl_key, "body", brand), ctx)
    footer_note = format_text(get_field(tpl_key, "footer_note", brand), ctx)
    hero_image = get_field(tpl_key, "hero_image", brand)
    cta_label = format_text(get_field(tpl_key, "cta", brand), ctx) if _has_field(tpl_key, "cta") else ""
    cta = (cta_label, cta_href) if cta_label and cta_href else None
    plain = plain_text(body, rows=rows, cta=cta, footer_note=footer_note or None, brand=brand)
    custom_raw = get_field(tpl_key, "custom_html", brand)
    if (custom_raw or "").strip():
        rich = merge_render_context(tpl_key, ctx, title, body, footer_note, hero_image, rows, cta, brand)
        html = format_text(custom_raw, rich)
    else:
        html = html_shell(title, body, rows=rows, cta=cta, footer_note=footer_note or None,
                          brand=brand, hero_image=hero_image)
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
    if tpl_key == "contact_ack":
        return base
    return {k: v for k, v in base.items() if k not in ("order_number",)}


def preview_rows(tpl_key):
    if tpl_key.startswith("order_"):
        return [("Order", "OK-4012"), ("Store", "Center City"), ("Total", "$24.47")]
    if tpl_key == "welcome":
        return [("Name", "Alex Morgan"), ("Email", "alex@example.com")]
    if tpl_key == "gift_card":
        return [("Code", "GIFT-OK-1234"), ("Value", "$25.00"), ("From", "Jordan")]
    if tpl_key == "contact_ack":
        return [("Subject", "Catering enquiry"), ("What you sent", "Office lunch for 20 people.")]
    return None


def _has_field(tpl_key, field):
    if field == "custom_html":
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
