"""Which storefront paths may show promo popup / mobile header chip."""

PROMO_PAGE_CHOICES = (
    ("home", "Home"),
    ("menu", "Menu & items"),
    ("deals", "Deals"),
    ("locations", "Locations"),
    ("about", "About"),
    ("contact", "Contact"),
    ("catering", "Catering"),
    ("cart", "Cart"),
    ("checkout", "Checkout"),
    ("account", "Account & orders"),
    ("rewards", "Rewards"),
    ("gift_cards", "Gift cards"),
    ("news", "News"),
    ("faq", "FAQ"),
    ("careers", "Careers"),
    ("builder", "Extra pages (/p/…)"),
)

ALL_PROMO_PAGE_IDS = frozenset(pid for pid, _ in PROMO_PAGE_CHOICES)


def normalize_show_pages(raw, legacy_default_all=True):
    """Saved list of page ids; legacy configs with no list default to all pages."""
    if raw is None:
        return sorted(ALL_PROMO_PAGE_IDS) if legacy_default_all else []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return sorted(ALL_PROMO_PAGE_IDS) if legacy_default_all else []
    out = []
    for item in raw:
        pid = str(item).strip()
        if pid in ALL_PROMO_PAGE_IDS and pid not in out:
            out.append(pid)
    if not out:
        return sorted(ALL_PROMO_PAGE_IDS)
    return out


def page_id_for_request_path(path):
    p = (path or "").split("?")[0].rstrip("/") or "/"
    if p.startswith("/admin"):
        return None
    if p == "/":
        return "home"
    if p == "/menu" or p.startswith("/menu/") or p.startswith("/item/"):
        return "menu"
    if p == "/deals" or p.startswith("/deals/"):
        return "deals"
    if p == "/locations" or p.startswith("/locations/"):
        return "locations"
    if p == "/about":
        return "about"
    if p == "/contact":
        return "contact"
    if p == "/catering":
        return "catering"
    if p == "/cart":
        return "cart"
    if p == "/checkout" or p.startswith("/checkout/") or p == "/order-confirmed":
        return "checkout"
    if p.startswith("/account") or p == "/orders" or p.startswith("/orders/") or p == "/favorites":
        return "account"
    if p == "/rewards":
        return "rewards"
    if p == "/gift-cards":
        return "gift_cards"
    if p == "/news":
        return "news"
    if p == "/faq":
        return "faq"
    if p == "/careers":
        return "careers"
    if p.startswith("/p/"):
        return "builder"
    return None


def promo_shown_on_path(show_pages, path):
    pages = show_pages if isinstance(show_pages, list) else []
    if not pages:
        # Empty list (e.g. accidental save) — treat as all pages; use banner "enabled" to hide.
        return True
    pid = page_id_for_request_path(path)
    if not pid:
        return False
    return pid in pages
