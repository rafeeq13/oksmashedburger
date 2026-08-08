"""Site-wide theme — the brand palette, type and shape, editable by the client.

The palette used to live only in premium.css, so changing the brand colour or
the corner radius meant editing a stylesheet. These are `SiteSetting` rows now
and get emitted as a small `:root{}` block in the page head, which lands after
every stylesheet and therefore wins without a single `!important`.

Only tokens that are actually referenced by the CSS are exposed. Anything the
client leaves blank simply is not emitted, so the built-in value stays.
"""
from app.models.site import SiteSetting

# key, label, CSS custom property, input type, built-in value, help
THEME_TOKENS = [
    # ── colour ────────────────────────────────────────────────────────────
    ("theme_primary", "Primary / brand", "--ok-yellow", "color", "#FFC72C",
     "Buttons, highlights, the yellow everywhere."),
    ("theme_primary_dark", "Primary (darker)", "--ok-amber", "color", "#E0A200",
     "Hover states and small text on light backgrounds."),
    ("theme_ink", "Ink / near-black", "--ok-ink", "color", "#0E0E0E",
     "Headings, dark sections, the black buttons."),
    ("theme_body", "Body text", "--ok-lux-gray", "color", "#8A8480",
     "Paragraphs and secondary copy."),
    ("theme_cream", "Cream / tint", "--ok-warm-white", "color", "#FCFAF6",
     "The soft off-white behind alternating sections."),
    ("theme_beige", "Beige panel", "--ok-beige", "color", "#F3ECE1",
     "Icon tiles and quieter panels."),
    ("theme_hairline", "Hairline / borders", "--ok-hairline", "color", "#E3E1DE",
     "Card borders and dividers."),

    # ── shape ─────────────────────────────────────────────────────────────
    ("theme_radius_control", "Button & field radius", "--r-control", "px", "8",
     "Corner radius on every button and form field."),
    ("theme_radius_card", "Card radius", "--r-card", "px", "16",
     "Corner radius on cards and panels."),

    # ── type ──────────────────────────────────────────────────────────────
    ("theme_font_display", "Heading font", "--ok-font-display", "font",
     "'Poppins', 'Inter', sans-serif", "Used for every heading."),
    ("theme_font_body", "Body font", "--ok-font-body", "font",
     "'Quicksand', sans-serif", "Used for paragraphs, buttons and fields."),
]

# What the font dropdown offers. Each is already loaded by the page, so picking
# one costs nothing extra — no new webfont request, no layout shift.
FONT_CHOICES = [
    ("'Poppins', 'Inter', sans-serif", "Poppins — geometric, confident"),
    ("'Quicksand', sans-serif", "Quicksand — rounded, friendly"),
    ("'Inter', system-ui, sans-serif", "Inter — neutral, highly legible"),
    ("Georgia, 'Times New Roman', serif", "Georgia — classic serif"),
    ("system-ui, -apple-system, 'Segoe UI', sans-serif", "System — fastest, native look"),
]

TOKEN_BY_KEY = {t[0]: t for t in THEME_TOKENS}


def theme_values():
    """Saved overrides only — a key that was never set is absent, not blank."""
    keys = [t[0] for t in THEME_TOKENS]
    return {s.key: s.value for s in SiteSetting.query.filter(SiteSetting.key.in_(keys)).all()
            if s.value}


def theme_css():
    """The `:root{}` block for the page head. Empty string when the client has
    not overridden anything, so the default build ships untouched."""
    saved = theme_values()
    if not saved:
        return ""
    parts = []
    for key, _label, prop, kind, _default, _help in THEME_TOKENS:
        val = (saved.get(key) or "").strip()
        if not val:
            continue
        if kind == "px":
            # stored as a bare number so the admin can use a slider
            val = "%spx" % val.rstrip("px").strip()
        parts.append("%s:%s" % (prop, val))

    if not parts:
        return ""

    css = ":root{" + ";".join(parts) + "}"

    # The font tokens are new: nothing in the existing stylesheets reads them
    # yet, so wire them to the families the site actually uses. Scoped to the
    # storefront body class so the admin panel keeps its own type.
    fd = (saved.get("theme_font_display") or "").strip()
    fb = (saved.get("theme_font_body") or "").strip()
    if fd:
        css += ("body :is(h1,h2,h3,h4,.ok-title,.ok-display,.ok-h2,.font-display)"
                "{font-family:%s !important}" % fd)
    if fb:
        css += "body{font-family:%s !important}" % fb
    return css
