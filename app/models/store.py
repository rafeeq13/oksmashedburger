"""Multi-location stores + per-store hours, delivery zones and INTEGRATIONS.

Each location owns its own menu (see StoreMenuItem in menu.py) and its own
integration credentials (StoreIntegration) — Stripe/Square/Uber keys, etc.
"""
from datetime import datetime, timedelta, time as _time

from app.extensions import db
from .base import TimestampMixin


def _parse_hm(s):
    try:
        return datetime.strptime(s, "%H:%M").time()
    except (ValueError, TypeError):
        return None

# Providers a store can be independently connected to (SRS §5.2)
INTEGRATION_PROVIDERS = [
    "stripe",        # online card payments
    "square",        # in-store POS / reconciliation
    "uber_direct",   # third-party delivery dispatch
    "google_maps",   # geocoding / distance / store locator
    "firebase",      # push notifications
    "twilio",        # SMS
    "sendgrid",      # email
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
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    timezone = db.Column(db.String(40), default="America/New_York")

    tax_rate = db.Column(db.Numeric(5, 4), default=0.08)      # 8%
    currency = db.Column(db.String(3), default="USD")
    delivery_radius_miles = db.Column(db.Float, default=4.0)
    min_order_amount = db.Column(db.Numeric(8, 2), default=10.00)
    avg_prep_minutes = db.Column(db.Integer, default=15)

    # Tipping (shown at checkout) — the store controls whether tips are offered
    # and which quick-percent buttons appear.
    tips_enabled = db.Column(db.Boolean, default=True, nullable=False)
    tip_presets = db.Column(db.JSON, default=lambda: [15, 18, 20])

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    accepts_delivery = db.Column(db.Boolean, default=True)
    accepts_pickup = db.Column(db.Boolean, default=True)
    # Operational open/close — controlled by staff/admin. "accepting_orders" gates
    # ASAP pickup/delivery; "accepting_scheduled" gates order-ahead independently.
    accepting_orders = db.Column(db.Boolean, default=True, nullable=False)
    accepting_scheduled = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships
    hours = db.relationship("StoreHours", back_populates="store", cascade="all, delete-orphan")
    delivery_zones = db.relationship("StoreDeliveryZone", back_populates="store", cascade="all, delete-orphan")
    integrations = db.relationship("StoreIntegration", back_populates="store", cascade="all, delete-orphan")
    menu_items = db.relationship("StoreMenuItem", back_populates="store", cascade="all, delete-orphan")

    # ── Convenience ────────────────────────────────────────────
    @property
    def full_address(self):
        return f"{self.address_line}, {self.city}, {self.state} {self.zip_code}"

    def hours_for(self, weekday):
        """StoreHours row for a Python weekday (Mon=0…Sun=6)."""
        return next((h for h in self.hours if h.day_of_week == weekday), None)

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
        h = self.hours_for(datetime.now().weekday())
        if not h or h.is_closed:
            return "Closed today"
        return f"{h.open_time}–{h.close_time}"

    @property
    def open_now(self):
        """Accepting immediate (ASAP) pickup/delivery right now — respects the
        manual open/close toggle AND today's opening hours."""
        return bool(self.is_active and self.accepting_orders and self.is_open_at(datetime.now()))

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
        now = now or datetime.now()
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
                    continue  # product not on this store's menu
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
    """Per-store integration configuration — 'each location owns its integrations'.

    `config` holds provider-specific credentials/settings as JSON, e.g.:
      stripe  -> {"account_id": "...", "publishable_key": "...", "secret_key": "..."}
      square  -> {"location_id": "...", "access_token": "..."}
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
