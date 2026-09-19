"""Granular admin panel access — granted by super_admin per staff member."""

# (group_key, group_label, [(perm_key, label, path_prefix), ...])
ADMIN_PERMISSION_GROUPS = (
    ("management", "Management", (
        ("dashboard", "Dashboard", "/admin"),
        ("orders", "Orders", "/admin/orders"),
        ("customers", "Customers", "/admin/customers"),
        ("menu", "Menu", "/admin/menu"),
        ("coupons", "Deals & coupons", "/admin/coupons"),
        ("gift_cards", "Gift cards", "/admin/gift-cards"),
        ("reviews", "Reviews", "/admin/reviews"),
        ("messages", "Messages", "/admin/messages"),
        ("subscribers", "Subscribers", "/admin/subscribers"),
        ("drivers", "Drivers", "/admin/drivers"),
    )),
    ("website", "Website", (
        ("pages", "Pages", "/admin/canvas"),
        ("content", "Content lists", "/admin/content"),
        ("images", "Images", "/admin/site-images"),
        ("theme", "Brand & theme", "/admin/theme"),
        ("builder", "Extra pages", "/admin/builder"),
        ("features", "Features on / off", "/admin/features"),
        ("page_builder", "Page builder (legacy)", "/admin/page-builder"),
        ("page_content", "Page content (legacy)", "/admin/page-content"),
    )),
    ("setup", "Setup", (
        ("settings", "Store settings", "/admin/settings"),
        ("hours", "Opening hours", "/admin/hours"),
        ("integrations", "Integrations", "/admin/integrations"),
        ("email_templates", "Email templates", "/admin/email-templates"),
        ("notifications", "Notifications", "/admin/notifications"),
    )),
    ("administration", "Administration", (
        ("staff", "Staff", "/admin/staff"),
        ("locations", "Locations", "/admin/locations"),
    )),
)

ALL_PERMISSION_KEYS = frozenset(
    key for _g, _l, items in ADMIN_PERMISSION_GROUPS for key, _lbl, _path in items
)

_LEGACY_MANAGEMENT_KEYS = frozenset(
    key for _g, _l, items in ADMIN_PERMISSION_GROUPS if _g == "management"
    for key, _lbl, _path in items
)

_PATH_RULES = sorted(
    [(path, key) for _g, _l, items in ADMIN_PERMISSION_GROUPS for key, _lbl, path in items],
    key=lambda row: len(row[0]),
    reverse=True,
)

# Shared admin utilities (catalog, uploads) follow the parent area.
_EXTRA_PATH_RULES = (
    ("/admin/catalog", "menu"),
    ("/admin/inline-image", "images"),
    ("/admin/promo-banner", "images"),
    ("/admin/inline-promo-banner", "images"),
    ("/admin/inline-section-text", "pages"),
    ("/admin/inline-style", "pages"),
    ("/admin/email-image", "email_templates"),
    ("/admin/store/status", "dashboard"),
)


def permission_for_path(path):
    """Return the permission key for an admin URL, or None."""
    path = (path or "").rstrip("/") or "/"
    for prefix, key in _EXTRA_PATH_RULES:
        if path == prefix or path.startswith(prefix + "/"):
            return key
    for prefix, key in _PATH_RULES:
        if path == prefix or path.startswith(prefix + "/"):
            return key
    return None


def normalize_permissions(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.split(",") if p.strip()]
    if not isinstance(raw, (list, tuple, set)):
        return []
    out = []
    for item in raw:
        key = str(item).strip()
        if key in ALL_PERMISSION_KEYS and key not in out:
            out.append(key)
    return out


def permissions_from_form(form):
    return normalize_permissions(form.getlist("permissions"))


def permission_labels_for_user(user):
    perms = user_admin_permissions(user)
    labels = []
    for _group_key, _group_label, items in ADMIN_PERMISSION_GROUPS:
        for key, label, _path in items:
            if key in perms:
                labels.append(label)
    return labels


def permission_count_for_user(user):
    return len(user_admin_permissions(user))


def user_admin_permissions(user):
    if not user or not user.role:
        return set()
    if user.role.name == "super_admin":
        return set(ALL_PERMISSION_KEYS)
    stored = getattr(user, "admin_permissions", None)
    if stored is None:
        if user.role.name in ("franchise_owner", "store_manager"):
            return set(_LEGACY_MANAGEMENT_KEYS)
        return set()
    return set(normalize_permissions(stored))


def user_has_permission(user, perm_key):
    if not perm_key:
        return True
    return perm_key in user_admin_permissions(user)


def can_access_admin(user):
    if not user or not user.role or not user.is_active:
        return False
    if user.role.name == "super_admin":
        return True
    if user.role.name in ("franchise_owner", "store_manager", "kitchen_staff", "cashier", "driver"):
        return bool(user_admin_permissions(user))
    return False


def can_access_admin_path(user, path):
    if not can_access_admin(user):
        return False
    if user.role.name == "super_admin":
        return True
    perm = permission_for_path(path)
    if perm is None:
        return path.rstrip("/") in ("/admin", "")
    return user_has_permission(user, perm)
