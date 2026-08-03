"""Full-site audit: templates, routes, CSS, assets, accessibility, weight."""
import io
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())
ROOT = "app/templates"
STATIC = "app/static"
SKIP_DIRS = ("admin", "kds", "driver")
STOREFRONT = ["website", "menu", "cart", "checkout", "pages", "stores",
              "orders", "partials", "layouts"]

def files(dirs):
    for d in dirs:
        for dp, _x, fs in os.walk(os.path.join(ROOT, d)):
            for f in fs:
                if f.endswith(".html"):
                    yield os.path.join(dp, f)

def read(p):
    return io.open(p, encoding="utf-8", errors="ignore").read()

report = defaultdict(list)

# ---- 1. Jinja compiles -----------------------------------------------------
def check_templates():
    from wsgi import app
    env = app.jinja_env
    bad = []
    for dp, _x, fs in os.walk(ROOT):
        for f in fs:
            if not f.endswith(".html"):
                continue
            p = os.path.join(dp, f)
            name = os.path.relpath(p, ROOT).replace("\\", "/")
            try:
                env.get_template(name)
            except Exception as e:
                bad.append((name, str(e)[:90]))
    return bad

# ---- 2. CSS classes used but never defined ---------------------------------
def check_css():
    css = ["app/static/vendor/bootstrap/bootstrap.min.css", "app/static/css/style.css",
           "app/static/css/premium.css", "app/static/css/theme.css",
           "app/static/css/utils.css", "app/static/css/generated.css"]
    defined = set()
    for f in css:
        if not os.path.exists(f):
            continue
        for m in re.finditer(r"\.(-?[A-Za-z_][-\w]*)", read(f)):
            defined.add(m.group(1))
    used = Counter()
    where = {}
    IGNORE = re.compile(r"^(fa-|fab$|fas$|far$|if$|else$|elif$|endif$|endfor$|for$|in$|and$|or$|not$|is$)")
    for p in files(STOREFRONT):
        for m in re.finditer(r'class="([^"]*)"', read(p)):
            for t in m.group(1).split():
                t = t.lstrip("!")
                if not re.match(r"^-?[A-Za-z]", t) or "{" in t or "}" in t or "%" in t:
                    continue
                if IGNORE.match(t) or t in ("fa-solid", "fa-brands", "fa-regular"):
                    continue
                used[t] += 1
                where.setdefault(t, os.path.relpath(p, ROOT))
    return [(t, n, where[t]) for t, n in used.most_common() if t not in defined]

# ---- 3. static asset references that do not exist --------------------------
def check_assets():
    missing = []
    pat = re.compile(r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]")
    seen = set()
    for dp, _x, fs in os.walk(ROOT):
        for f in fs:
            if not f.endswith(".html"):
                continue
            p = os.path.join(dp, f)
            for m in pat.finditer(read(p)):
                rel = m.group(1)
                if rel in seen:
                    continue
                seen.add(rel)
                if not os.path.exists(os.path.join(STATIC, rel)):
                    missing.append((rel, os.path.relpath(p, ROOT)))
    return missing

# ---- 4. accessibility smells ----------------------------------------------
def check_a11y():
    out = Counter()
    detail = defaultdict(list)
    for p in files(STOREFRONT):
        s = read(p)
        rel = os.path.relpath(p, ROOT)
        for m in re.finditer(r"<img\b[^>]*>", s):
            if "alt=" not in m.group(0):
                out["img without alt"] += 1
                detail["img without alt"].append(rel)
        for m in re.finditer(r"<a\b[^>]*>\s*<i\b[^>]*></i>\s*</a>", s):
            if "aria-label" not in m.group(0):
                out["icon-only link without aria-label"] += 1
                detail["icon-only link without aria-label"].append(rel)
        for m in re.finditer(r"<button\b[^>]*>\s*<i\b[^>]*></i>\s*</button>", s):
            if "aria-label" not in m.group(0):
                out["icon-only button without aria-label"] += 1
                detail["icon-only button without aria-label"].append(rel)
        for m in re.finditer(r"<input\b[^>]*>", s):
            g = m.group(0)
            if 'type="hidden"' in g or 'type="submit"' in g:
                continue
            if "aria-label" not in g and "placeholder" not in g and "id=" not in g:
                out["input with no label/aria/placeholder"] += 1
                detail["input with no label/aria/placeholder"].append(rel)
    return out, detail

# ---- 5. leftovers / weight -------------------------------------------------
def check_leftovers():
    tw = Counter()
    for p in files(STOREFRONT):
        for m in re.finditer(r'class="([^"]*)"', read(p)):
            for t in m.group(1).split():
                if re.match(r"^!?([a-z-]+\[[^\]]*\]|(sm|md|lg|xl|hover|focus|group-hover):)", t):
                    tw[t] += 1
    return tw

def weigh():
    rows = []
    for base, _d, fs in os.walk(STATIC):
        for f in fs:
            p = os.path.join(base, f)
            if f.endswith((".css", ".js")) and "uploads" not in p:
                rows.append((os.path.relpath(p, STATIC).replace("\\", "/"),
                             os.path.getsize(p)))
    return sorted(rows, key=lambda r: -r[1])[:12]


def main():
    print("=" * 66)
    print("1. TEMPLATE COMPILE (all %d templates incl. admin)" % sum(1 for _ in files(["."])) if False else "1. TEMPLATE COMPILE")
    bad = check_templates()
    print("   broken: %d" % len(bad))
    for n, e in bad[:10]:
        print("     %-42s %s" % (n, e))

    print("\n2. CSS CLASSES USED WITH NO RULE ANYWHERE (storefront)")
    miss = check_css()
    print("   distinct: %d   total uses: %d" % (len(miss), sum(n for _, n, _ in miss)))
    for t, n, w in miss[:20]:
        print("     %4d  %-26s %s" % (n, t, w))

    print("\n3. MISSING STATIC ASSETS")
    ma = check_assets()
    print("   missing: %d" % len(ma))
    for rel, w in ma[:10]:
        print("     %-38s %s" % (rel, w))

    print("\n4. ACCESSIBILITY SMELLS (storefront)")
    a, det = check_a11y()
    if not a:
        print("   none found")
    for k, n in a.most_common():
        print("   %4d  %s" % (n, k))
        print("         e.g. %s" % ", ".join(sorted(set(det[k]))[:3]))

    print("\n5. TAILWIND LEFTOVERS (storefront)")
    tw = check_leftovers()
    print("   distinct: %d   uses: %d" % (len(tw), sum(tw.values())))
    for t, n in tw.most_common(10):
        print("     %4d  %s" % (n, t))

    print("\n6. ASSET WEIGHT (css/js)")
    for rel, sz in weigh():
        print("   %7.1f KB  %s" % (sz / 1024.0, rel))
    print("=" * 66)


if __name__ == "__main__":
    main()
