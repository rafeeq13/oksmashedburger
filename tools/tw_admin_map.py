"""Second-pass Tailwind -> CSS/Bootstrap rename for the ADMIN templates.

tools/tw2bs.py converts everything that has an exact Bootstrap or utils.css
equivalent. What is left in the admin panel is either a brand colour Tailwind
built from its config, a state variant (hover:/last:/active:), or a utility
Bootstrap does not ship. This pass renames those tokens to the `ok-*` classes
defined in app/static/css/admin.css.

Rules that keep this safe (both were learned the hard way):
  * it only ever touches the inside of a `class="..."` attribute,
  * it rewrites with a bounded regex and NEVER splits-and-dedupes the value,
    because a class attribute can also be a JS concat or a Jinja block where
    `'`, `+`, `{%` and `endif` legitimately repeat.

Usage:
    python tools/tw_admin_map.py <file-or-dir> [...]
    python tools/tw_admin_map.py --dry <file-or-dir> [...]
"""
import os
import re
import sys
from collections import Counter

# --- token -> new class ----------------------------------------------------
# "" means the token is dropped: the behaviour it carried is now expressed by a
# component class in admin.css (sidebar slide-in, toggle switch, ...).
MAP = {
    # --- Bootstrap has these under a different name -------------------------
    "ml-auto": "ms-auto",
    "font-mono": "font-monospace",
    "sm:inline": "d-sm-inline",

    # --- utilities Bootstrap does not ship ---------------------------------
    "min-h-0": "ok-min-h-0",
    "inset-y-0": "ok-inset-y-0",
    "normal-case": "ok-normal-case",
    "whitespace-pre-line": "ok-pre-line",
    "list-disc": "ok-list-disc",
    "border-dashed": "ok-border-dashed",
    "backdrop-blur": "ok-blur",
    "opacity-90": "ok-opacity-90",
    "rounded-t-lg": "ok-rounded-t-lg",
    "tracking-wide": "ok-ls-wide",
    "cursor-grab": "ok-grab",
    "animate-ping": "ok-ping",
    "ring-white": "ok-ring-white",
    "transition": "ok-transition",
    "transition-all": "ok-transition",
    "transition-colors": "ok-transition-colors",
    "transition-transform": "ok-transition-transform",
    "duration-150": "",           # the ok-transition* classes pin the duration
    "accent-okyellow": "ok-accent-yellow",
    "accent-okred": "ok-accent-red",

    # --- sizing -------------------------------------------------------------
    # NOTE: theme.css already owns .ok-mw-md/.ok-mw-lg on different numbers, so
    # Tailwind's max-w-* scale gets its own ok-maxw-* names.
    "max-w-md": "ok-maxw-md",
    "max-w-2xl": "ok-maxw-2xl",
    "max-w-3xl": "ok-maxw-3xl",
    "h-0.5": "ok-h-05", "h-2.5": "ok-h-25", "w-2.5": "ok-w-25",
    "h-13": "",                   # not on Tailwind's scale, so it never applied
    # axis gaps: Bootstrap's column-gap-*/row-gap-* scale skips 1.25rem/.75rem
    "gap-x-4": "column-gap-3", "gap-x-6": "column-gap-4",
    "gap-x-5": "ok-cgap-5", "gap-y-3": "ok-rgap-3",

    # --- grid column spans --------------------------------------------------
    "col-span-2": "ok-col-span-2", "col-span-3": "ok-col-span-3",
    "sm:col-span-2": "ok-col-span-sm-2", "sm:col-span-4": "ok-col-span-sm-4",
    "md:col-span-2": "ok-col-span-md-2",
    "lg:col-span-2": "ok-col-span-lg-2", "lg:col-span-3": "ok-col-span-lg-3",
    "lg:col-span-4": "ok-col-span-lg-4", "lg:col-span-6": "ok-col-span-lg-6",

    # --- offsets ------------------------------------------------------------
    "top-0.5": "ok-top-05", "top-1.5": "ok-top-15", "top-4": "ok-top-4",
    "left-0.5": "ok-left-05", "left-1.5": "ok-left-15", "left-4": "ok-left-4",
    "right-4": "ok-right-4", "bottom-4": "ok-bottom-4",

    # --- responsive spacing / sizing ---------------------------------------
    "sm:gap-3": "ok-gap-sm-3", "md:gap-3": "ok-gap-md-3",
    "lg:p-6": "ok-p-lg-6", "lg:px-6": "ok-px-lg-6", "md:pl-4": "ok-pl-md-4",
    "lg:w-60": "ok-w-lg-60", "lg:w-80": "ok-w-lg-80",
    "md:border-l": "ok-border-start-md",
    "md:border-paneledge": "ok-border-paneledge-md",
    "lg:pl-64": "",               # .adm-content owns the sidebar offset

    # --- lists / dividers ---------------------------------------------------
    "divide-y": "ok-divide-y",
    "divide-[var(--ok-line)]": "",
    "last:border-0": "ok-last-border-0",

    # --- brand colours Tailwind built from its config -----------------------
    "bg-okamber": "bg-amber", "bg-okamber/10": "bg-amber-10",
    "bg-okamber/90": "bg-amber-90",
    "bg-okgreen/10": "bg-ok-green-10", "bg-okgreen/15": "bg-ok-green-15",
    "bg-okgreen/20": "bg-ok-green-20",
    "bg-okred/10": "bg-ok-red-10", "bg-okred/60": "bg-ok-red-60",
    "bg-okyellow/10": "bg-yellow-10", "bg-okyellow/20": "bg-yellow-20",
    "bg-softyellow/20": "bg-cream-20", "bg-softyellow/40": "bg-cream-40",
    "bg-jet/5": "bg-ink-05", "bg-slate/40": "bg-muted-40",
    "border-black/5": "border-ink-05",
    "bg-panel": "bg-panel", "border-paneledge": "border-paneledge",
    # the few raw Tailwind palette colours the admin reached for
    "bg-gray-200": "bg-gray-200", "bg-gray-300": "bg-gray-300",
    "bg-red-500": "bg-red-500", "text-red-400": "text-red-400",
    "text-green-400": "text-green-400", "text-amber-500": "text-amber-500",
    "bg-amber-50": "bg-amber-50", "border-amber-200": "border-amber-200",
    # colours written inside a JS/Jinja expression, so tw2bs skipped them
    "text-slate": "text-muted-warm", "text-okred": "text-ok-red",
    "text-okgreen": "text-ok-green", "text-okamber": "text-gold",
    "text-okyellow": "text-yellow", "text-jet": "text-ink",
    "border-okyellow": "border-yellow",

    # --- state variants -> real classes ------------------------------------
    "hover:bg-black/5": "ok-hov-bg-ink-05",
    "hover:bg-white/10": "ok-hov-bg-w-10",
    "hover:bg-ok-red/10": "ok-hov-bg-red-10",
    "hover:bg-okred/10": "ok-hov-bg-red-10",
    "hover:bg-red-500/10": "ok-hov-bg-red-10",
    "hover:text-jet": "ok-hov-text-ink",
    "hover:text-okred": "ok-hov-text-red",
    "hover:text-white": "ok-hov-text-white",
    "hover:border-okyellow": "ok-hov-border-yellow",
    "hover:underline": "ok-hov-underline",
    "active:cursor-grabbing": "",      # .ok-grab:active covers it

    # --- expressed by a component class in admin.css ------------------------
    "bg-gradient-to-b": "", "from-[#16181f]": "", "to-[#101216]": "",
    "-translate-x-full": "", "lg:translate-x-0": "",
    "peer": "", "peer-checked:translate-x-0": "", "peer-checked:block": "",
    "peer-checked:bg-okgreen": "", "peer-checked:translate-x-5": "",

    # --- Tailwind-only body/html classes with no CSS behind them -----------
    "font-body": "", "antialiased": "", "scroll-smooth": "",
}

# `!utility` forced a Tailwind !important. Our layers already load after
# style.css, and every utils.css colour class carries !important of its own, so
# the bang is dropped and the plain class does the same job.
BANG = {
    "!text-xs": "ok-fs-xs", "!text-okred": "text-ok-red", "!mb-1": "mb-1",
    "!bg-okred/10": "bg-ok-red-10", "!text-okamber": "text-gold",
    "!text-[.65rem]": "text-[.65rem]",   # left for tw_arbitrary.py
}
MAP.update(BANG)

# Longest first so `bg-okamber/10` is tried before `bg-okamber`.
_KEYS = sorted(MAP, key=len, reverse=True)
# A token boundary: any character that can be part of a Tailwind class name.
_EDGE = r"A-Za-z0-9_:/\[\]\.\-!"
TOKEN_RE = re.compile(
    r"(?<![%s])(%s)(?![%s])" % (_EDGE, "|".join(re.escape(k) for k in _KEYS), _EDGE)
)
CLASS_RE = re.compile(r'class="([^"]*)"')

hits = Counter()


def rewrite_value(val):
    def sub(m):
        tok = m.group(1)
        hits[tok] += 1
        return MAP[tok]
    out = TOKEN_RE.sub(sub, val)
    # dropped tokens leave double spaces behind
    return re.sub(r" {2,}", " ", out).strip(" ") if out.strip() else out


def process(path, dry):
    src = open(path, encoding="utf-8").read()
    new = CLASS_RE.sub(lambda m: 'class="%s"' % rewrite_value(m.group(1)), src)
    if new != src and not dry:
        open(path, "w", encoding="utf-8", newline="").write(new)
    return new != src


def main():
    args = [a for a in sys.argv[1:] if a != "--dry"]
    dry = "--dry" in sys.argv
    files = []
    for t in args:
        if os.path.isdir(t):
            for root, _d, names in os.walk(t):
                files += [os.path.join(root, n) for n in names if n.endswith(".html")]
        else:
            files.append(t)
    touched = sum(1 for f in files if process(f, dry))
    print("%s %d/%d files, %d tokens rewritten"
          % ("would change" if dry else "renamed", touched, len(files), sum(hits.values())))
    unused = [k for k in MAP if not hits[k]]
    if unused:
        print("\nmappings that matched nothing (%d): %s" % (len(unused), ", ".join(sorted(unused))))


if __name__ == "__main__":
    main()
