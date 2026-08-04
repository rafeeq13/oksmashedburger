"""Build a Lucide sprite covering every Font Awesome icon the site uses.

Font Awesome Solid is a filled, fairly heavy set. Lucide is the modern
stroke equivalent: same idea, thinner, rounder, consistent. Brand marks
(Instagram, Visa, Apple…) stay on Font Awesome Brands — Lucide dropped
brand icons on purpose and there is no replacement.

Output: app/static/img/icons.svg — one <symbol> per icon, referenced with
<use href="#i-name">. One request, cached forever, no JS library.
"""
import os
import re
import sys
import urllib.request

BASE = "https://cdn.jsdelivr.net/npm/lucide-static@latest/icons/%s.svg"

# fa name -> lucide name
MAP = {
    "align": "align-justify", "align-center": "align-center",
    "align-left": "align-left", "align-right": "align-right",
    "angles-left": "chevrons-left", "arrow-down": "arrow-down",
    "arrow-left": "arrow-left", "arrow-pointer": "mouse-pointer-2",
    "arrow-right": "arrow-right", "arrow-rotate-left": "rotate-ccw",
    "arrow-trend-down": "trending-down", "arrow-trend-up": "trending-up",
    "arrow-up": "arrow-up", "arrow-up-right-from-square": "external-link",
    "bag-shopping": "shopping-bag", "ban": "ban", "bars": "menu",
    "bell": "bell", "bolt": "zap", "border-all": "table",
    "briefcase": "briefcase", "bullhorn": "megaphone", "burger": "beef",
    "burst": "sparkle", "cake-candles": "cake",
    "calendar-check": "calendar-check", "calendar-day": "calendar",
    "calendar-days": "calendar-days", "car": "car",
    "cart-shopping": "shopping-cart", "chart-line": "line-chart",
    "check": "check", "chevron-down": "chevron-down",
    "chevron-left": "chevron-left", "chevron-right": "chevron-right",
    "chevron-up": "chevron-up", "circle-check": "circle-check",
    "circle-exclamation": "circle-alert", "circle-info": "info",
    "circle-notch": "loader-circle", "circle-xmark": "circle-x",
    "clock": "clock", "clone": "copy", "code": "code",
    "comment": "message-circle", "comment-sms": "message-square-text",
    "credit-card": "credit-card", "door-closed": "door-closed",
    "door-open": "door-open", "download": "download", "envelope": "mail",
    "expand": "maximize", "eye": "eye", "eye-slash": "eye-off",
    "file-arrow-down": "file-down", "file-pdf": "file-text",
    "fire-burner": "flame", "floppy-disk": "save", "football": "trophy",
    "forward-step": "skip-forward", "gauge-high": "gauge", "gear": "settings",
    "gift": "gift", "graduation-cap": "graduation-cap",
    "grip-vertical": "grip-vertical", "hand": "hand", "hands-clapping": "party-popper",
    "heart": "heart", "house": "house", "image": "image",
    "layer-group": "layers", "link": "link", "link-slash": "link-2-off",
    "location-arrow": "navigation", "location-dot": "map-pin", "lock": "lock",
    "magnifying-glass": "search", "medal": "medal",
    "mobile-screen-button": "smartphone", "palette": "palette",
    "paper-plane": "send", "pen": "pen", "pen-ruler": "pen-tool",
    "pen-to-square": "square-pen", "pencil": "pencil", "phone": "phone",
    "play": "play", "plug": "plug", "plus": "plus", "receipt": "receipt",
    "right-from-bracket": "log-out", "rotate-left": "rotate-ccw",
    "rotate-right": "rotate-cw", "sack-dollar": "banknote",
    "shield-halved": "shield-check", "sliders": "sliders-horizontal",
    "spinner": "loader-circle", "star": "star",
    "star-half-stroke": "star-half", "store": "store", "tag": "tag",
    "trash": "trash-2", "triangle-exclamation": "triangle-alert",
    "truck": "truck", "up-right-from-square": "external-link",
    "user": "user", "user-plus": "user-plus", "users": "users",
    "wand-magic-sparkles": "wand-sparkles", "xmark": "x",
    "utensils": "utensils", "drumstick-bite": "drumstick",
    "glass-water": "cup-soda", "leaf": "leaf", "desktop": "monitor",
    "user-gear": "user-cog", "file-lines": "file-text", "list-ul": "list",
    "table-cells-large": "layout-grid", "envelope-open-text": "mail-open",
    "car-side": "car", "circle-question": "circle-help", "info": "info",
    "filter": "filter", "arrows-rotate": "refresh-cw", "print": "printer",
    "square-check": "square-check-big", "money-bill": "banknote",
    "wallet": "wallet", "box": "package", "boxes-stacked": "boxes",
    "clipboard": "clipboard", "wheat-awn": "wheat", "seedling": "sprout",
    "carrot": "carrot", "fish": "fish", "egg": "egg", "cheese": "cake-slice",
    "pepper-hot": "flame", "bacon": "beef", "cow": "beef", "bowl-food": "soup",
    "ice-cream": "ice-cream-cone", "mug-hot": "coffee", "bottle-water": "cup-soda", "chart-pie": "chart-pie", "percent": "percent",
}

out, missing = [], []
for fa, lu in sorted(set(MAP.items())):
    try:
        with urllib.request.urlopen(BASE % lu, timeout=25) as r:
            svg = r.read().decode("utf-8")
    except Exception as e:
        missing.append("%s -> %s (%s)" % (fa, lu, e))
        continue
    m = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S)
    if not m:
        missing.append("%s -> %s (no body)" % (fa, lu))
        continue
    body = re.sub(r"\s+", " ", m.group(1)).strip()
    out.append('<symbol id="i-%s" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">%s</symbol>'
               % (fa, body))

dest = os.path.join("app", "static", "img", "icons.svg")
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "w", encoding="utf-8") as f:
    f.write('<svg xmlns="http://www.w3.org/2000/svg" style="display:none">'
            + "".join(out) + "</svg>")

print("symbols written:", len(out))
print("size:", round(os.path.getsize(dest) / 1024, 1), "KB")
if missing:
    print("MISSING (%d):" % len(missing))
    for m in missing:
        print("   ", m)
