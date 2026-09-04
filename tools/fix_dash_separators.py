"""Replace em-dash-style 'n/a' separators with comma or pipe (not code math)."""
import os
import re
import sys

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".cursor"}
SKIP_FILES = {"bootstrap.min.css"}
EXTS = {".py", ".html", ".js", ".css", ".md", ".txt", ".json"}

CODE_LINE = re.compile(
    r"(\{\{[^}]*\s-\s[^}]*\}\})|"
    r"(calc\([^)]+\))|"
    r"(\s-\s*\d+\b)|"
    r"(\b\d+\s-\s)|"
    r"(offsetLeft|offsetWidth|clientWidth|clientHeight|lastLen|availW|availH|"
    r"Math\.|\.length|flow\.index|min_order|loyalty_points|balance\s-\s|"
    r"total\s-\sactive|qty\s-\s1|points\|int\s-\s|hi\s-\s|lo\s-\s|"
    r"sqrt\(1\s-\s|1\s-\sscale|w\s-\s36|dataset\.dist|grid-column:\s*1\s*/\s*-1|"
    r"--ok-|\(1\s-\s[a-zA-Z])",
    re.I,
)


def transform_segment(text):
    t = text
    t = t.replace(" - OK Smashed Burger", " | OK Smashed Burger")
    t = re.sub(r'"n/a"', '"n/a"', t)
    t = re.sub(r"'n/a'", "'n/a'", t)
    t = re.sub(r"(%s)\s-\s(%s)", r"\1 | \2", t)
    t = re.sub(r"(\$[\d.,]+)\s-\s", r"\1 | ", t)
    t = re.sub(
        r"([A-Za-z][\w\s]{0,40}?)\s-\s([a-z])",
        lambda m: m.group(1) + " | " + m.group(2),
        t,
    )
    t = t.replace("n/a", ", ")
    return t


def process_line(line):
    if "n/a" not in line:
        return line
    if CODE_LINE.search(line):
        return line
    parts = re.split(r'("[^"]*"|\'[^\']*\')', line)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
        else:
            out.append(transform_segment(part))
    return "".join(out)


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    changed = 0
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            if fn in SKIP_FILES:
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS:
                continue
            path = os.path.join(root, fn)
            try:
                text = open(path, encoding="utf-8").read()
            except Exception:
                continue
            if "n/a" not in text:
                continue
            lines = text.splitlines(keepends=True)
            new_lines = [process_line(ln) for ln in lines]
            new = "".join(new_lines)
            if new != text:
                open(path, "w", encoding="utf-8", newline="").write(new)
                changed += 1
    print("files_changed:", changed)
    return 0


def pass2():
    """Targeted fixes the first pass cannot safely reach (quoted placeholders, etc.)."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pairs = [
        ('"n/a"', '"n/a"'),
        ("'n/a'", "'n/a'"),
        ("%s | %s", "%s | %s"),
        (". | {b}", ". | {b}"),
        ("complete, enjoy", "complete, enjoy"),
        ("factory | OK", "factory | OK"),
        ("breakdown | same", "breakdown | same"),
        ("checkout | push", "checkout | push"),
        ("catalog | create", "catalog | create"),
        ("heading | pick", "heading | pick"),
        ("view | assigned", "view | assigned"),
        ("order | refund", "order | refund"),
        ("log | one", "log | one"),
        ("helpers | per-store", "helpers | per-store"),
        ("Optional | verifies", "Optional | verifies"),
        ("only, drop", "only, drop"),
        ("Could not add, please", "Could not add, please"),
        ("is not a mail server hostname, use", "is not a mail server hostname, use"),
        ("Could not resolve '%s', check", "Could not resolve '%s', check"),
        ("Nothing was saved, the", "Nothing was saved, the"),
        ("Test email was not sent, check", "Test email was not sent, check"),
        ("Application ID | use", "Application ID | use"),
        ("skip handler, no", "skip handler, no"),
        (" | provider metadata, charges", " | provider metadata, charges"),
    ]
    changed = 0
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            if fn in SKIP_FILES:
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS:
                continue
            path = os.path.join(root, fn)
            try:
                text = open(path, encoding="utf-8").read()
            except Exception:
                continue
            new = text
            for old, new_val in pairs:
                new = new.replace(old, new_val)
            if new != text:
                open(path, "w", encoding="utf-8", newline="").write(new)
                changed += 1
    print("pass2_files_changed:", changed)


if __name__ == "__main__":
    main()
    pass2()
    raise SystemExit(0)
