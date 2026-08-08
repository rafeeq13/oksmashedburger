"""Tailwind -> Bootstrap/CSS converter for the OK Smashed Burger storefront.

Deterministic, token-by-token rewrite of `class="..."` attributes. Every mapping
is exact-value: Bootstrap's class is used when its computed value matches the
Tailwind one, otherwise a pinned ok-* utility from utils.css is used. Anything
unmapped is left untouched and reported, so nothing is silently dropped.

Usage:
    python tools/tw2bs.py <file-or-dir> [...]        # rewrite in place
    python tools/tw2bs.py --dry <file-or-dir> [...]  # report only
"""
import os
import re
import sys
from collections import Counter

# --- exact 1:1 renames -----------------------------------------------------
MAP = {
    # display
    "flex": "d-flex", "inline-flex": "d-inline-flex", "block": "d-block",
    "inline-block": "d-inline-block", "inline": "d-inline", "hidden": "d-none",
    "grid": "ok-grid",
    # flex
    "flex-col": "flex-column", "flex-row": "flex-row",
    "flex-wrap": "flex-wrap", "flex-nowrap": "flex-nowrap",
    "flex-1": "flex-grow-1", "grow": "flex-grow-1", "shrink-0": "flex-shrink-0",
    "items-center": "align-items-center", "items-start": "align-items-start",
    "items-end": "align-items-end", "items-baseline": "align-items-baseline",
    "items-stretch": "align-items-stretch",
    "justify-center": "justify-content-center", "justify-between": "justify-content-between",
    "justify-end": "justify-content-end", "justify-start": "justify-content-start",
    "self-start": "align-self-start", "self-center": "align-self-center",
    "self-end": "align-self-end", "self-stretch": "align-self-stretch",
    "place-items-center": "ok-place-center",
    # position
    "relative": "position-relative", "absolute": "position-absolute",
    "fixed": "position-fixed", "sticky": "position-sticky",
    "inset-0": "ok-fill", "top-0": "top-0", "bottom-0": "bottom-0",
    "left-0": "start-0", "right-0": "end-0",
    # sizing
    "w-full": "w-100", "h-full": "h-100", "w-auto": "w-auto", "h-auto": "h-auto",
    "max-w-full": "mw-100", "min-h-screen": "min-vh-100", "min-w-0": "ok-min-w-0",
    "object-cover": "ok-cover", "object-contain": "ok-contain",
    # text
    "text-left": "text-start", "text-right": "text-end", "text-center": "text-center",
    "uppercase": "text-uppercase", "lowercase": "text-lowercase",
    "capitalize": "text-capitalize", "truncate": "text-truncate",
    "italic": "fst-italic", "underline": "text-decoration-underline",
    "whitespace-nowrap": "text-nowrap", "break-all": "text-break",
    "font-normal": "fw-normal", "font-medium": "fw-medium",
    "font-semibold": "fw-semibold", "font-bold": "fw-bold",
    "font-extrabold": "ok-fw-800", "font-black": "ok-fw-900",
    "leading-none": "ok-lh-none", "leading-tight": "ok-lh-tight",
    "leading-snug": "ok-lh-snug", "leading-relaxed": "ok-lh-relaxed",
    # misc
    "mx-auto": "mx-auto", "cursor-pointer": "ok-pointer",
    "select-none": "ok-nodrag", "pointer-events-none": "pe-none",
    "overflow-hidden": "overflow-hidden", "overflow-x-auto": "overflow-x-auto",
    "overflow-y-auto": "overflow-y-auto",
    "border": "border", "border-0": "border-0",
    "border-t": "border-top", "border-b": "border-bottom",
    "border-l": "border-start", "border-r": "border-end",
    "rounded-full": "rounded-pill", "rounded": "ok-rounded",
    "rounded-md": "ok-rounded-md", "rounded-lg": "ok-rounded-lg",
    "rounded-xl": "ok-rounded-xl", "rounded-2xl": "ok-rounded-2xl",
    "rounded-3xl": "ok-rounded-3xl",
    "z-10": "ok-z-10", "z-20": "ok-z-20", "z-30": "ok-z-30",
    "z-40": "ok-z-40", "z-50": "ok-z-50",
    "opacity-0": "ok-opacity-0", "opacity-25": "ok-opacity-25",
    "opacity-30": "ok-opacity-30", "opacity-35": "ok-opacity-35",
    "opacity-60": "ok-opacity-60",
    "shadow-sm": "ok-shadow-sm", "shadow-md": "ok-shadow-md",
    "shadow-lg": "ok-shadow-lg", "shadow-xl": "ok-shadow-xl",
    "shadow-2xl": "ok-shadow-2xl", "shadow": "ok-shadow-md",
    "aspect-square": "ok-aspect-square",
    "group": "ok-hovergroup",
    "ring-2": "ok-ring-2", "ring-4": "ok-ring-4",
    "sr-only": "visually-hidden",
    # brand colours
    "text-jet": "text-ink", "text-slate": "text-muted-warm", "text-okamber": "text-gold",
    "text-okyellow": "text-yellow", "text-okgreen": "text-ok-green",
    "text-okred": "text-ok-red", "text-okbrandred": "text-brandred",
    "bg-jet": "bg-ink", "bg-okyellow": "bg-yellow", "bg-softyellow": "bg-cream",
    "bg-okgreen": "bg-ok-green", "bg-okred": "bg-ok-red",
    "border-jet": "border-ink", "border-okyellow": "border-yellow",
    "border-okred": "border-ok-red",
}

# opacity-suffixed colours: tw `text-white/70` -> `text-w-70`
OPACITY = {
    "text-white": "text-w-{o}", "bg-white": "bg-w-{o}",
    "text-jet": "text-ink-{o}", "text-slate": "text-muted-warm-{o}",
    "text-okyellow": "text-yellow-{o}", "bg-okyellow": "bg-yellow-{o}",
    "bg-softyellow": "bg-cream-{o}", "bg-okgreen": "bg-ok-green-{o}",
    "bg-okred": "bg-ok-red-{o}", "bg-black": "bg-black-{o}",
    "border-jet": "border-ink-{o}", "border-okyellow": "border-yellow-{o}",
    "border-white": "border-w-{o}", "border-okgreen": "border-ok-green-{o}",
}

# spacing: tailwind step -> (bootstrap step or None). None => pinned ok-* class.
BS_SPACE = {"0": "0", "1": "1", "2": "2", "4": "3", "6": "4", "12": "5"}
SPACE_SUFFIX = {"0.5": "05", "1.5": "15", "2.5": "25", "3.5": "35"}
SIDE_BS = {"t": "t", "b": "b", "l": "s", "r": "e", "x": "x", "y": "y", "": ""}

TEXT_SIZE = {"xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl"}
GRID_COLS = re.compile(r"^grid-cols-(\d+)$")
SPACE_RE = re.compile(r"^([mp])([tblrxy]?)-(\d+(?:\.\d)?)$")
GAP_RE = re.compile(r"^gap-(\d+(?:\.\d)?)$")
WH_RE = re.compile(r"^([wh])-(\d+)$")
SPACEY_RE = re.compile(r"^space-y-(\d+(?:\.\d)?)$")
TEXTSIZE_RE = re.compile(r"^text-(xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl)$")
COLOR_OP_RE = re.compile(r"^([a-z-]+)/(\d+)$")
# What a CSS class name can look like. Anything else in a class attribute is
# code (a JS concat, a Jinja fragment) and must survive the de-duplication pass.
CLASSNAME_RE = re.compile(r"^!?[A-Za-z][A-Za-z0-9_:./\[\]%-]*$")

unmapped = Counter()


def step_suffix(n):
    return SPACE_SUFFIX.get(n, n.replace(".", ""))


def convert_token(tok, bp=""):
    """bp is '', 'sm', 'md', 'lg', 'xl' (responsive prefix already stripped)."""
    # exact renames (only safe unprefixed, except display/grid handled below)
    if not bp and tok in MAP:
        return MAP[tok]

    if bp:
        if tok == "hidden":
            return "d-%s-none" % bp
        if tok in ("flex", "block", "inline-flex", "inline-block", "grid"):
            word = {"flex": "flex", "block": "block", "inline-flex": "inline-flex",
                    "inline-block": "inline-block", "grid": "grid"}[tok]
            return "d-%s-%s" % (bp, word)
        if tok == "flex-col":
            return "flex-%s-column" % bp
        if tok == "flex-row":
            return "flex-%s-row" % bp
        if tok == "text-center":
            return "text-%s-center" % bp
        if tok == "items-center":
            return "align-items-%s-center" % bp

    m = COLOR_OP_RE.match(tok)
    if m and m.group(1) in OPACITY and not bp:
        return OPACITY[m.group(1)].format(o=m.group(2))

    m = TEXTSIZE_RE.match(tok)
    if m:
        return ("ok-fs-%s-%s" % (bp, m.group(1))) if bp else ("ok-fs-%s" % m.group(1))

    m = GRID_COLS.match(tok)
    if m:
        return ("ok-grid-%s-%s" % (bp, m.group(1))) if bp else ("ok-grid-%s" % m.group(1))

    m = WH_RE.match(tok)
    if m and not bp and m.group(2) not in ("100",):
        return "ok-%s-%s" % (m.group(1), m.group(2))

    m = SPACE_RE.match(tok)
    if m and not bp:
        prop, side, n = m.groups()
        if n in BS_SPACE:
            return "%s%s-%s" % (prop, SIDE_BS[side], BS_SPACE[n])
        return "ok-%s%s-%s" % (prop, side, step_suffix(n))

    m = GAP_RE.match(tok)
    if m and not bp:
        n = m.group(1)
        return "gap-%s" % BS_SPACE[n] if n in BS_SPACE else "ok-gap-%s" % step_suffix(n)

    m = SPACEY_RE.match(tok)
    if m and not bp:
        return "ok-stack-%s" % step_suffix(m.group(1))

    unmapped[(bp + ":" if bp else "") + tok] += 1
    return None


def convert_class_attr(value):
    out = []
    for tok in value.split():
        if not tok:
            continue
        bp = ""
        bare = tok
        for p in ("sm:", "md:", "lg:", "xl:", "2xl:"):
            if tok.startswith(p):
                bp, bare = p[:-1], tok[len(p):]
                break
        # leave already-converted, jinja, arbitrary, state-variant and ok-* tokens alone
        if (bare.startswith(("ok-", "btn", "badge", "chip", "fa-", "d-", "bs-",
                             "align-", "justify-", "position-", "text-", "fw-",
                             "flex-", "border-", "rounded-", "bg-", "w-1", "h-1"))
                and bare in ("",)):
            pass
        if "[" in bare or "{" in tok or ":" in bare or bare.startswith("!"):
            out.append(tok)
            unmapped[tok] += 1 if "[" in bare or ":" in bare else 0
            continue
        new = convert_token(bare, bp)
        out.append(new if new else tok)
    # De-duplicate, keep order. Only real class names are ever dropped: a
    # `class="..."` can also be a JS/Jinja expression building the value, where
    # `'` and `+` legitimately repeat and removing a repeat corrupts the code.
    seen, final = set(), []
    for t in out:
        if not CLASSNAME_RE.match(t):
            final.append(t)
            continue
        if t not in seen:
            seen.add(t)
            final.append(t)
    return " ".join(final)


JINJA_RE = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.S)


def convert_mixed(value):
    """Convert a class attribute that also contains Jinja.

    Only the plain-text segments are tokenised. A token sitting flush against a
    `{{ ... }}` expression is left alone, because the expression may be building
    part of the class name itself.
    """
    parts = JINJA_RE.split(value)
    out = []
    for i, seg in enumerate(parts):
        if JINJA_RE.fullmatch(seg or ""):
            out.append(seg)
            continue
        if not seg:
            out.append(seg)
            continue
        prev_interp = i > 0 and parts[i - 1].startswith("{{")
        next_interp = i + 1 < len(parts) and parts[i + 1].startswith("{{")
        lead = " " if seg[:1].isspace() else ""
        trail = " " if seg[-1:].isspace() else ""
        toks = seg.split()
        if not toks:
            out.append(seg)
            continue
        conv = []
        for j, tok in enumerate(toks):
            glued_left = (j == 0 and not lead and prev_interp)
            glued_right = (j == len(toks) - 1 and not trail and next_interp)
            if glued_left or glued_right:
                conv.append(tok)
                continue
            conv.append(convert_class_attr(tok))
        out.append(lead + " ".join(conv) + trail)
    return "".join(out)


def process(path, dry):
    src = open(path, encoding="utf-8").read()

    def repl(m):
        val = m.group(1)
        conv = convert_mixed(val) if ("{" in val) else convert_class_attr(val)
        return 'class="%s"' % conv

    new = re.sub(r'class="([^"]*)"', repl, src)
    changed = new != src
    if changed and not dry:
        open(path, "w", encoding="utf-8", newline="").write(new)
    return changed


def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    targets = [a for a in args if a != "--dry"]
    files = []
    for t in targets:
        if os.path.isdir(t):
            for root, _d, names in os.walk(t):
                files += [os.path.join(root, n) for n in names if n.endswith(".html")]
        else:
            files.append(t)
    touched = sum(1 for f in files if process(f, dry))
    print("%s %d/%d files" % ("would change" if dry else "converted", touched, len(files)))
    if unmapped:
        print("\nleft untouched (needs a component class or is already fine):")
        for tok, n in unmapped.most_common(40):
            print("  %4d  %s" % (n, tok))


if __name__ == "__main__":
    main()
