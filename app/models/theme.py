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
    # ── brand colour ──────────────────────────────────────────────────────
    ("theme_primary", "Primary / brand", "--ok-yellow", "color", "#FFC72C",
     "Buttons, badges, highlights — the yellow everywhere.", "Colour"),
    ("theme_primary_dark", "Primary (darker)", "--ok-amber", "color", "#E0A200",
     "Hover states, small yellow text on light backgrounds, the squiggle.", "Colour"),
    ("theme_ink", "Ink / near-black", "--ok-ink", "color", "#0E0E0E",
     "Headings, dark sections, black buttons, the footer.", "Colour"),
    ("theme_body", "Body text", "--ok-lux-gray", "color", "#8A8480",
     "Paragraphs and secondary copy across every page.", "Colour"),
    ("theme_link", "Link colour", "--ok-link", "color", "#0E0E0E",
     "Text links inside copy — not buttons.", "Colour"),

    # ── surfaces ──────────────────────────────────────────────────────────
    ("theme_cream", "Cream / tint", "--ok-warm-white", "color", "#FCFAF6",
     "The soft off-white behind alternating sections.", "Surfaces"),
    ("theme_beige", "Beige panel", "--ok-beige", "color", "#F3ECE1",
     "Icon tiles and quieter panels.", "Surfaces"),
    ("theme_card", "Card background", "--ok-card-bg", "color", "#FFFFFF",
     "Every card and panel on the site.", "Surfaces"),
    ("theme_hairline", "Hairline / borders", "--ok-hairline", "color", "#E3E1DE",
     "Card borders, dividers and form-field outlines.", "Surfaces"),
    ("theme_header_bg", "Header background", "--ok-header-bg", "color", "#FFFFFF",
     "The bar across the top of every page.", "Surfaces"),
    ("theme_footer_bg", "Footer background", "--ok-footer-bg", "color", "#0E0E0E",
     "The block at the bottom of every page.", "Surfaces"),

    # ── status colour ─────────────────────────────────────────────────────
    ("theme_success", "Success / open", "--ok-green", "color", "#2E7D32",
     "“Open now”, order confirmed, free-delivery badges.", "Status"),
    ("theme_danger", "Error / closed", "--ok-red", "color", "#C62828",
     "“Closed”, form errors, delete actions.", "Status"),

    # ── shape ─────────────────────────────────────────────────────────────
    ("theme_radius_control", "Button & field radius", "--r-control", "px", "8",
     "Corner radius on every button and form field.", "Shape"),
    ("theme_radius_card", "Card radius", "--r-card", "px", "16",
     "Corner radius on cards and panels.", "Shape"),
    ("theme_radius_image", "Image radius", "--r-media", "px", "12",
     "Corner radius on photos inside cards.", "Shape"),
    ("theme_shadow", "Card shadow", "--sh-2", "shadow",
     "0 2px 6px rgba(28,22,16,.05), 0 10px 24px -6px rgba(28,22,16,.10)",
     "How much every card lifts off the page.", "Shape"),

    # ── type ──────────────────────────────────────────────────────────────
    ("theme_font_display", "Heading font", "--ok-font-display", "font",
     "'Poppins', 'Inter', sans-serif", "Every heading, on every page.", "Type"),
    ("theme_font_body", "Body font", "--ok-font-body", "font",
     "'Quicksand', sans-serif", "Paragraphs, buttons and form fields.", "Type"),
    ("theme_font_scale", "Text size", "--ok-font-scale", "pct", "100",
     "Scales all body copy up or down together. 100 is the built-in size.", "Type"),

    # ── layout ────────────────────────────────────────────────────────────
    ("theme_container", "Content width", "--ok-container", "px", "1200",
     "How wide the content column runs before it stops growing.", "Layout"),
    ("theme_section_space", "Space between sections", "--ok-section-space", "px", "72",
     "The vertical rhythm between one section and the next.", "Layout"),
]

THEME_GROUPS = ["Colour", "Surfaces", "Status", "Shape", "Type", "Layout"]

SHADOW_PRESETS = [
    ("", "Built-in"),
    ("none", "Flat — no shadow"),
    ("0 1px 2px rgba(28,22,16,.06)", "Barely there"),
    ("0 2px 6px rgba(28,22,16,.05), 0 10px 24px -6px rgba(28,22,16,.10)", "Soft (built-in)"),
    ("0 6px 18px rgba(28,22,16,.10), 0 24px 48px -12px rgba(28,22,16,.18)", "Lifted"),
    ("0 12px 32px rgba(28,22,16,.16), 0 40px 80px -20px rgba(28,22,16,.28)", "Dramatic"),
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


# A few tokens have to write more than one custom property, because the site
# grew two names for the same idea (--ok-ink and --ok-jet are both "near
# black"; radius.css has its own --ok-radius). Emitting the aliases is what
# makes those controls actually land instead of looking live and doing nothing.
TOKEN_ALIASES = {
    "theme_ink": ["--ok-jet"],
    "theme_body": ["--ok-slate"],
    "theme_radius_control": ["--ok-radius"],
}


def theme_css():
    """The `:root{}` block for the page head. Empty string when the client has
    not overridden anything, so the default build ships untouched."""
    saved = theme_values()
    if not saved:
        return ""
    parts = []
    for key, _label, prop, kind, _default, _help, _group in THEME_TOKENS:
        val = (saved.get(key) or "").strip()
        if not val:
            continue
        if kind == "px":
            # stored as a bare number so the admin can use a slider
            val = "%spx" % val.rstrip("px").strip()
        elif kind == "pct":
            val = val.rstrip("%").strip()      # the rule does the maths
        parts.append("%s:%s" % (prop, val))
        for alias in TOKEN_ALIASES.get(key, []):
            parts.append("%s:%s" % (alias, val))

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
