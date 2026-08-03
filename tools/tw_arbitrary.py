"""Convert Tailwind arbitrary values and responsive prefixes into real CSS.

Scans the storefront templates, works out the CSS property behind every
`prop-[value]` and `bp:class` token, emits a rule for each into
app/static/css/generated.css, and rewrites the templates to use the new
class name. Anything it cannot map with certainty is left alone and printed,
so a token is never silently dropped.
"""
import io
import os
import re
import sys
from collections import OrderedDict

ROOTS = ["app/templates/website", "app/templates/menu", "app/templates/cart",
         "app/templates/checkout", "app/templates/pages", "app/templates/stores",
         "app/templates/orders", "app/templates/partials", "app/templates/layouts"]
OUT = "app/static/css/generated.css"
BP = {"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1280px"}

# arbitrary prefix -> (css property, short slug)
PROP = {
    "text": ("font-size", "fs"), "w": ("width", "w"), "h": ("height", "h"),
    "min-w": ("min-width", "minw"), "max-w": ("max-width", "maxw"),
    "min-h": ("min-height", "minh"), "max-h": ("max-height", "maxh"),
    "p": ("padding", "p"), "px": ("padding-inline", "px"), "py": ("padding-block", "py"),
    "pt": ("padding-top", "pt"), "pb": ("padding-bottom", "pb"),
    "pl": ("padding-left", "pl"), "pr": ("padding-right", "pr"),
    "m": ("margin", "m"), "mx": ("margin-inline", "mx"), "my": ("margin-block", "my"),
    "mt": ("margin-top", "mt"), "mb": ("margin-bottom", "mb"),
    "ml": ("margin-left", "ml"), "mr": ("margin-right", "mr"),
    "gap": ("gap", "gap"), "z": ("z-index", "z"), "top": ("top", "top"),
    "bottom": ("bottom", "bottom"), "left": ("left", "left"), "right": ("right", "right"),
    "rounded": ("border-radius", "r"), "tracking": ("letter-spacing", "ls"),
    "leading": ("line-height", "lh"), "aspect": ("aspect-ratio", "ar"),
    "basis": ("flex-basis", "basis"), "grid-cols": ("grid-template-columns", "gc"),
    "opacity": ("opacity", "op"), "text-shadow": ("text-shadow", "tsh"),
}
COLOR_PROP = {"text": "color", "bg": "background-color", "border": "border-color",
              "ring": "box-shadow", "fill": "fill", "stroke": "stroke"}


SPACE_P = {"p": "padding", "px": "padding-inline", "py": "padding-block",
           "pt": "padding-top", "pb": "padding-bottom", "pl": "padding-left",
           "pr": "padding-right", "m": "margin", "mx": "margin-inline",
           "my": "margin-block", "mt": "margin-top", "mb": "margin-bottom",
           "gap": "gap", "top": "top", "bottom": "bottom", "left": "left",
           "right": "right", "w": "width", "h": "height",
           "space-y": "__stack", "basis": "flex-basis"}
FS = {"xs": ".75rem", "sm": ".875rem", "base": "1rem", "lg": "1.125rem",
      "xl": "1.25rem", "2xl": "1.5rem", "3xl": "1.875rem", "4xl": "2.25rem",
      "5xl": "3rem", "6xl": "3.75rem", "7xl": "4.5rem"}
KEYWORD = {
    "sticky": ("position", "sticky"), "relative": ("position", "relative"),
    "absolute": ("position", "absolute"), "static": ("position", "static"),
    "justify-self-end": ("justify-self", "end"),
    "justify-self-start": ("justify-self", "start"),
    "self-auto": ("align-self", "auto"), "self-end": ("align-self", "flex-end"),
    "mx-auto": ("margin-inline", "auto"), "w-auto": ("width", "auto"),
    "h-auto": ("height", "auto"), "w-full": ("width", "100%"),
    "h-full": ("height", "100%"), "text-nowrap": ("white-space", "nowrap"),
    "whitespace-nowrap": ("white-space", "nowrap"),
    "order-1": ("order", "1"), "order-2": ("order", "2"),
}
NUM_RE = re.compile(r"^(-?)([a-z-]+)-(\d+(?:\.\d+)?)$")
COLSPAN_RE = re.compile(r"^col-span-(\d+)$")
GRIDCOLS_RE = re.compile(r"^grid-cols-(\d+)$")
FS_RE = re.compile(r"^text-(xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl)$")


def plain_value(tok):
    """(property, value) for a plain Tailwind utility, or None."""
    if tok in KEYWORD:
        return KEYWORD[tok]
    m = FS_RE.match(tok)
    if m:
        return ("font-size", FS[m.group(1)])
    m = COLSPAN_RE.match(tok)
    if m:
        return ("grid-column", "span %s/span %s" % (m.group(1), m.group(1)))
    m = GRIDCOLS_RE.match(tok)
    if m:
        return ("grid-template-columns", "repeat(%s,minmax(0,1fr))" % m.group(1))
    m = NUM_RE.match(tok)
    if m:
        neg, prefix, num = m.groups()
        if prefix in SPACE_P and SPACE_P[prefix] != "__stack":
            rem = float(num) * 0.25
            v = ("%g" % rem) + "rem"
            return (SPACE_P[prefix], ("-" + v) if neg else v)
    return None

ARB = re.compile(r"^(-?)([a-z-]+)\[([^\]]+)\]$")
RESP = re.compile(r"^(sm|md|lg|xl):(.+)$")

rules = OrderedDict()
skipped = OrderedDict()


def slugify(v):
    s = re.sub(r"[^a-zA-Z0-9]+", "", v)
    return s[:18].lower() or "x"


def decode(value):
    """Tailwind writes spaces as underscores inside arbitrary values."""
    return value.replace("_", " ")


def arbitrary(tok):
    m = ARB.match(tok)
    if not m:
        return None
    neg, prefix, raw = m.groups()
    prefix = prefix.rstrip("-")
    val = decode(raw)
    if prefix in ("text", "bg", "border", "fill", "stroke") and (
            val.startswith("#") or val.startswith("rgb") or val.startswith("var(")):
        prop, slug = COLOR_PROP[prefix], {"text": "c", "bg": "bgc", "border": "bc",
                                          "fill": "fill", "stroke": "stroke"}[prefix]
    elif prefix in PROP:
        prop, slug = PROP[prefix]
    else:
        return None
    if neg:
        val = "-" + val
    name = "ok-%s-%s" % (slug, slugify(val))
    rules.setdefault(name, (prop, val))
    return name


def responsive(tok):
    m = RESP.match(tok)
    if not m:
        return None
    bp, rest = m.groups()
    # already-Bootstrap responsive tokens are left alone
    if rest.startswith(("d-", "text-", "flex-", "align-items", "align-self", "justify-content")):
        return None
    inner = arbitrary(rest)
    if inner:
        prop, val = rules[inner]
        name = "%s-%s" % (inner, bp)
        rules.setdefault(name, (prop, val, bp))
        return name
    pv = plain_value(rest)
    if pv:
        prop, val = pv
        name = "ok-%s-%s-%s" % (re.sub(r"[^a-z]", "", prop)[:6], slugify(val), bp)
        rules.setdefault(name, (prop, val, bp))
        return name
    return None


def convert(tok):
    return arbitrary(tok) or responsive(tok)


def walk_files():
    for r in ROOTS:
        for dp, _d, fs in os.walk(r):
            for f in fs:
                if f.endswith(".html"):
                    yield os.path.join(dp, f)


def main():
    dry = "--dry" in sys.argv
    changed = 0
    for path in walk_files():
        src = io.open(path, encoding="utf-8").read()

        def repl(m):
            val = m.group(1)
            out = []
            for tok in val.split(" "):
                if not tok or "{" in tok or "}" in tok:
                    out.append(tok)
                    continue
                bang = tok.startswith("!")
                bare = tok[1:] if bang else tok
                if "[" not in bare and ":" not in bare:
                    out.append(tok)
                    continue
                if bare.startswith(("hover:", "focus:", "group-hover:", "group-focus")):
                    skipped.setdefault(bare, 0)
                    skipped[bare] += 1
                    out.append(tok)
                    continue
                new = convert(bare)
                if new:
                    out.append(("!" + new) if bang else new)
                else:
                    skipped.setdefault(bare, 0)
                    skipped[bare] += 1
                    out.append(tok)
            return 'class="%s"' % " ".join(out)

        new_src = re.sub(r'class="([^"]*)"', repl, src)
        if new_src != src:
            changed += 1
            if not dry:
                io.open(path, "w", encoding="utf-8", newline="").write(new_src)

    if not dry and not rules:
        print('no arbitrary tokens found; leaving generated.css untouched')
    elif not dry:
        lines = ["/* =========================================================",
                 "   GENERATED — do not hand-edit.",
                 "   Every rule here replaces one Tailwind arbitrary value or",
                 "   responsive utility. Regenerate with tools/tw_arbitrary.py",
                 "   ========================================================= */"]
        plain = [(n, r) for n, r in rules.items() if len(r) == 2]
        resp = [(n, r) for n, r in rules.items() if len(r) == 3]
        for n, (prop, val) in plain:
            lines.append(".%s{%s:%s}" % (n, prop, val))
        for bp, width in BP.items():
            block = [(n, r) for n, r in resp if r[2] == bp]
            if not block:
                continue
            lines.append("@media (min-width:%s){" % width)
            for n, (prop, val, _b) in block:
                lines.append("  .%s{%s:%s}" % (n, prop, val))
            lines.append("}")
        io.open(OUT, "w", encoding="utf-8", newline="").write("\n".join(lines) + "\n")

    print("%s %d files, generated %d rules" %
          ("would change" if dry else "changed", changed, len(rules)))
    if skipped:
        print("\nleft for manual handling (%d distinct):" % len(skipped))
        for tok, n in sorted(skipped.items(), key=lambda kv: -kv[1])[:25]:
            print("  %3d  %s" % (n, tok))


if __name__ == "__main__":
    main()
