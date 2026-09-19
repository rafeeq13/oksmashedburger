"""Multi-location stores + per-store hours, delivery zones and INTEGRATIONS.

Each location owns its own menu (see StoreMenuItem in menu.py) and its own
integration credentials (StoreIntegration), Stripe/Square/Uber keys, etc.
"""
import re
from datetime import datetime, timedelta, time as _time

from app.extensions import db
from .base import TimestampMixin


def normalize_map_embed(val):
    """Accept a Google embed URL or a pasted <iframe> snippet."""
    val = (val or "").strip()
    if not val:
        return ""
    m = re.search(r'src=["\']([^"\']+)', val, re.I)
    return m.group(1).strip() if m else val


def coords_from_map_url(url):
    """Parse lat/lng from a Google Maps or embed URL when present."""
    from urllib.parse import unquote

    url = unquote((url or "").strip())
    if not url:
        return None
    m = re.search(r'!3d([-\d.]+)!4d([-\d.]+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'!2d([-\d.]+)!3d([-\d.]+)', url)
    if m:
        return float(m.group(2)), float(m.group(1))
    m = re.search(r'@([-\d.]+),([-\d.]+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'[?&]q=([^&]+)', url)
    if m:
        q = unquote(m.group(1).replace('+', ' ')).strip()
        parts = [p.strip() for p in q.split(',')]
        if len(parts) == 2:
            try:
                lat, lng = float(parts[0]), float(parts[1])
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return lat, lng
            except (TypeError, ValueError):
                pass
    return None


def _parse_hm(s):
    """Parse 'HH:MM' opening-hours string to time."""
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip(), "%H:%M").time()
    except (ValueError, TypeError):
        return None


def _store_tz(store):
    from zoneinfo import ZoneInfo

    tz_name = (store.timezone if store else None) or "America/New_York"
    for name in (tz_name, "America/New_York", "UTC"):
        try:
            return ZoneInfo(name)
        except Exception:
            continue
    return ZoneInfo("UTC")


def query_from_map_url(url):
    """Return the ?q= search text from a locations-page style embed URL."""
    from urllib.parse import unquote

    url = unquote((url or "").strip())
    if not url:
        return None
    m = re.search(r'[?&]q=([^&]+)', url)
    if not m:
        return None
    q = unquote(m.group(1).replace('+', ' ')).strip()
    if not q:
        return None
    if coords_from_map_url(f"?q={q}") is not None:
        return None
    return q

# Providers a store can be independently connected to (SRS §5.2)
INTEGRATION_PROVIDERS = [
    "stripe",        # online card payments
    "square",        # in-store POS / reconciliation
    "uber_direct",   # third-party delivery dispatch
    "google_maps",   # geocoding / distance / store locator
    "firebase",      # push notifications
    "twilio",        # SMS
    "smtp",          # email (SMTP)
]


class Store(TimestampMixin, db.Model):
    __tablename__ = "stores"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, index=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)          # e.g. "Center City"
    phone = db.Column(db.String(30))
    email = db.Column(db.String(255))

    address_line = db.Column(db.String(255))
    city = db.Column(db.String(80), default="Philadelphia")
    state = db.Column(db.String(40), default="PA")
    zip_code = db.Column(db.String(12))
    image_url = db.Column(db.String(500))           # optional location photo
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    map_embed_url = db.Column(db.String(500))   # Google Maps Share → Embed map
    timezone = db.Column(db.String(40), default="America/New_York")

    tax_rate = db.Column(db.Numeric(5, 4), default=0.08)      # 8%
    currency = db.Column(db.String(3), default="USD")
    delivery_radius_miles = db.Column(db.Float, default=4.0)
    min_order_amount = db.Column(db.Numeric(8, 2), default=10.00)
    avg_prep_minutes = db.Column(db.Integer, default=15)

    # Tipping (shown at checkout), the store controls whether tips are offered
    # and which quick-percent buttons appear.
    tips_enabled = db.Column(db.Boolean, default=True, nullable=False)
    tip_presets = db.Column(db.JSON, default=lambda: [15, 18, 20])

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    accepts_delivery = db.Column(db.Boolean, default=True)
    accepts_pickup = db.Column(db.Boolean, default=True)
    # Operational open/close | controlled by staff/admin. "accepting_orders" gates
    # ASAP pickup/delivery; "accepting_scheduled" gates order-ahead independently.
    accepting_orders = db.Column(db.Boolean, default=True, nullable=False)
    accepting_scheduled = db.Column(db.Boolean, default=True, nullable=False)
    # sandbox = test credentials / simulated fallbacks; production = live keys only
    integration_env = db.Column(db.String(20), default="sandbox", nullable=False)

    # Relationships
    hours = db.relationship("StoreHours", back_populates="store", cascade="all, delete-orphan")
    delivery_zones = db.relationship("StoreDeliveryZone", back_populates="store", cascade="all, delete-orphan")
    integrations = db.relationship("StoreIntegration", back_populates="store", cascade="all, delete-orphan")
    menu_items = db.relationship("StoreMenuItem", back_populates="store", cascade="all, delete-orphan")

    # ── Convenience ────────────────────────────────────────────
    @property
    def full_address(self):
        return f"{self.address_line}, {self.city}, {self.state} {self.zip_code}"

    @property
    def admin_label(self):
        """Short location label for admin store switchers."""
        name = (self.name or "").strip()
        street = (self.address_line or "").strip()
        zip_code = (self.zip_code or "").strip()
        short = ", ".join(p for p in (street, zip_code) if p)
        if name and short:
            return f"{name} | {short}"
        return name or short or self.full_address

    @property
    def admin_switcher_label(self):
        """Address-only label for the admin top-bar store switcher."""
        street = (self.address_line or "").strip()
        zip_code = (self.zip_code or "").strip()
        short = ", ".join(p for p in (street, zip_code) if p)
        return short or self.full_address

    @property
    def map_query(self):
        if self.latitude is not None and self.longitude is not None:
            return f"{self.latitude},{self.longitude}"
        return self.full_address

    @property
    def map_pin_coords(self):
        """Lat/lng parsed from the locations page map embed URL."""
        return coords_from_map_url(self.map_embed_src)

    @property
    def map_embed_geocode_query(self):
        """Address query from the locations page embed, when not numeric coords."""
        if self.map_pin_coords:
            return None
        return query_from_map_url(self.map_embed_src) or self.full_address

    @property
    def map_embed_src(self):
        if self.map_embed_url:
            return self.map_embed_url
        from urllib.parse import quote
        return f"https://maps.google.com/maps?q={quote(self.map_query)}&z=15&output=embed"

    def contact_hours_lines(self):
        labels = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        lines = []
        for i, label in enumerate(labels):
            h = self.hours_for(i)
            if not h or h.is_closed:
                lines.append(f"{label}: Closed")
            else:
                lines.append(f"{label}: {h.open_time}–{h.close_time}")
        return lines

    def hours_for(self, weekday):
        """StoreHours row for a Python weekday (Mon=0…Sun=6)."""
        return next((h for h in self.hours if h.day_of_week == weekday), None)

    def local_now(self):
        """Current date/time in this store's timezone (naive local)."""
        now = datetime.now(_store_tz(self))
        if now.tzinfo is not None:
            return now.replace(tzinfo=None)
        return now

    def is_open_at(self, dt):
        """Is the store within its opening hours at datetime dt?"""
        if not self.is_active:
            return False
        h = self.hours_for(dt.weekday())
        if not h or h.is_closed:
            return False
        o, c = _parse_hm(h.open_time), _parse_hm(h.close_time)
        if o is None or c is None:
            return True  # hours not configured -> treat as always open
        t = dt.time()
        if c == _time(0, 0):        # closes at midnight = end of day
            return t >= o
        if c <= o:                  # overnight window (e.g. 18:00–02:00)
            return t >= o or t < c
        return o <= t < c

    @property
    def today_hours(self):
        now = self.local_now()
        h = self.hours_for(now.weekday())
        if not h or h.is_closed:
            return "Closed today"
        return f"{h.open_time}–{h.close_time}"

    @property
    def today_hours_with_day(self):
        labels = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        now = self.local_now()
        day = labels[now.weekday()]
        h = self.hours_for(now.weekday())
        if not h or h.is_closed:
            return f"{day}: Closed"
        return f"{day}: {h.open_time}–{h.close_time}"

    @property
    def open_now(self):
        """Accepting immediate (ASAP) pickup/delivery right now | respects the
        manual open/close toggle AND today's opening hours."""
        return bool(self.is_active and self.accepting_orders and self.is_open_at(self.local_now()))

    @property
    def asap_unavailable_reason(self):
        """Why ASAP orders show as closed (None if open_now). For admin messaging."""
        if not self.is_active:
            return "This location is inactive."
        if not self.accepting_orders:
            return "Staff closed ASAP orders (dashboard “Close store”) — hours unchanged."
        if not self.is_open_at(self.local_now()):
            h = self.hours_for(self.local_now().weekday())
            if not h or h.is_closed:
                return "Today is marked closed in opening hours."
            return f"Outside today’s window ({h.open_time}–{h.close_time} {self.timezone or 'America/New_York'})."
        return None

    @property
    def scheduling_open(self):
        """Accepting order-ahead (scheduled) orders (specific time is validated
        against opening hours at checkout)."""
        return bool(self.is_active and self.accepting_scheduled)

    @property
    def can_order(self):
        return self.open_now or self.scheduling_open

    # ── Scheduling slots ──────────────────────────────────────────────
    # The picker used to be a bare datetime field, so a customer could choose
    # 03:00 on a day the store shuts at 23:00 and only find out at checkout.
    # These are the times the store can actually accept, generated from its own
    # opening hours, and the same helper validates what comes back.
    SCHED_DAYS = 7           # how far ahead a customer may book
    SCHED_STEP = 15          # minutes between slots
    SCHED_LEAD = 30          # minimum notice, so the kitchen can make it

    def schedule_days(self, now=None):
        """[{date, label, slots:[{value,label}]}] for the next SCHED_DAYS days.

        A day with no open hours is skipped entirely rather than shown empty,
        and today only offers times that are still reachable.
        """
        now = now or self.local_now()
        earliest = now + timedelta(minutes=self.SCHED_LEAD)
        out = []
        for offset in range(self.SCHED_DAYS):
            day = (now + timedelta(days=offset)).date()
            h = self.hours_for(day.weekday())
            if not h or h.is_closed:
                continue
            o, c = _parse_hm(h.open_time), _parse_hm(h.close_time)
            if o is None or c is None:
                continue
            start = datetime.combine(day, o)
            # a close time at or before the open time means it runs past midnight
            end = datetime.combine(day, c)
            if c <= o:
                end += timedelta(days=1)

            slots, t = [], start
            while t < end:
                if t >= earliest:
                    slots.append({"value": t.strftime("%Y-%m-%dT%H:%M"),
                                  "label": t.strftime("%I:%M %p").lstrip("0")})
                t += timedelta(minutes=self.SCHED_STEP)
            if not slots:
                continue
            out.append({
                "date": day.isoformat(),
                "label": ("Today" if offset == 0 else
                          "Tomorrow" if offset == 1 else day.strftime("%a %b %d")),
                "hours": "%s–%s" % (h.open_time, h.close_time),
                "slots": slots,
            })
        return out

    def accepts_schedule_at(self, value, now=None):
        """Is `value` ("YYYY-MM-DDTHH:MM") a slot this store actually offers?"""
        if not value:
            return False
        return any(value == s["value"]
                   for d in self.schedule_days(now) for s in d["slots"])

    def integration(self, provider):
        return next((i for i in self.integrations if i.provider == provider), None)

    def is_connected(self, provider):
        i = self.integration(provider)
        return bool(i and i.enabled)

    def effective_menu(self):
        """Return this store's menu grouped by category, with per-store price
        and availability applied. This is what makes each location's menu its own."""
        from .menu import Category
        by_product = {mi.product_id: mi for mi in self.menu_items}
        result = []
        cats = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        for cat in cats:
            items = []
            for product in sorted(cat.products, key=lambda p: p.sort_order):
                # `is_active` is the catalogue-wide switch; the item page and
                # modal both 404 on an inactive product, so listing one here
                # produced a card that did nothing when tapped.
                if not product.is_active:
                    continue
                mi = by_product.get(product.id)
                if not mi or not mi.is_listed:
                    continue  # not on this store's menu
                items.append({
                    "product": product,
                    "price": float(mi.price_override if mi.price_override is not None else product.base_price),
                    "available": mi.is_available,
                    "featured": mi.is_featured,
                })
            if items:
                result.append({"category": cat, "items": items})
        return result


class StoreHours(db.Model):
    __tablename__ = "store_hours"
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)   # 0=Mon … 6=Sun
    open_time = db.Column(db.String(5))                   # "11:00"
    close_time = db.Column(db.String(5))                  # "23:00"
    is_closed = db.Column(db.Boolean, default=False)
    store = db.relationship("Store", back_populates="hours")


class StoreDeliveryZone(db.Model):
    __tablename__ = "store_delivery_zones"
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    name = db.Column(db.String(80))
    zip_codes = db.Column(db.JSON, default=list)          # ["19102", "19103"]
    radius_miles = db.Column(db.Float, default=3.0)       # delivery radius from the store
    delivery_fee = db.Column(db.Numeric(6, 2), default=2.99)
    min_order = db.Column(db.Numeric(8, 2), default=10.00)
    est_minutes = db.Column(db.Integer, default=30)       # estimated delivery time
    color = db.Column(db.String(20), default="#E0A200")   # map/legend colour
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    store = db.relationship("Store", back_populates="delivery_zones")


class StoreIntegration(TimestampMixin, db.Model):
    """Per-store integration configuration, 'each location owns its integrations'.

    `config` holds provider-specific credentials/settings as JSON, e.g.:
      stripe  -> {"account_id": "...", "publishable_key": "...", "secret_key": "..."}
      square  -> {"application_id": "...", "location_id": "...", "access_token": "..."}
      uber    -> {"customer_id": "...", "client_id": "...", "client_secret": "..."}
    Secrets should be stored encrypted / in a vault in production (SRS NFR-2.2).
    """
    __tablename__ = "store_integrations"
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    provider = db.Column(db.String(40), nullable=False)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    config = db.Column(db.JSON, default=dict)
    store = db.relationship("Store", back_populates="integrations")

    __table_args__ = (
        db.UniqueConstraint("store_id", "provider", name="uq_store_provider"),
    )
