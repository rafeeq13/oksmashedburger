"""Users & Role-Based Access Control (SRS §2.3, §4.1)."""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.extensions import db
from .base import TimestampMixin

_ph = PasswordHasher()

user_stores = db.Table(
    "user_stores",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    db.Column("store_id", db.Integer, db.ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True),
)

# The 8 user classes from SRS §2.3
ROLES = [
    "super_admin", "franchise_owner", "store_manager", "kitchen_staff",
    "cashier", "driver", "customer", "guest",
]


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)
    description = db.Column(db.String(255))

    users = db.relationship("User", back_populates="role")


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255))
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    avatar_url = db.Column(db.String(500))          # uploaded photo; falls back to initials

    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    role = db.relationship("Role", back_populates="users")

    # Staff are scoped to store(s). store_id is set when pinned to one location.
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"))
    store = db.relationship("Store", foreign_keys=[store_id])
    stores = db.relationship("Store", secondary=user_stores, lazy="select")

    # Admin areas this user may open (set by super_admin on Staff screen).
    admin_permissions = db.Column(db.JSON, nullable=True)

    loyalty_points = db.Column(db.Integer, default=0, nullable=False)

    def set_password(self, raw):
        self.password_hash = _ph.hash(raw)

    def check_password(self, raw):
        try:
            return _ph.verify(self.password_hash, raw)
        except VerifyMismatchError:
            return False

    @property
    def initials(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        if parts:
            return "".join(p[0] for p in parts[:2]).upper()
        return (self.email or "?")[0].upper()

    @property
    def full_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.email

    def assigned_stores(self):
        """Active stores this user may access in admin."""
        from app.helpers import active_stores

        if self.role and self.role.name == "super_admin":
            return active_stores()
        if self.stores:
            return [s for s in self.stores if s.is_active]
        if self.store_id and self.store:
            return [self.store] if self.store.is_active else []
        return []

    def assigned_store_ids(self):
        return {s.id for s in self.assigned_stores()}

    def sync_primary_store(self):
        """Keep store_id aligned with assigned stores (single = pinned)."""
        ids = [s.id for s in self.stores] if self.stores else []
        if len(ids) == 1:
            self.store_id = ids[0]
        elif len(ids) > 1:
            self.store_id = None

    def set_assigned_stores(self, store_list):
        self.stores = list(store_list or [])
        if self.stores:
            self.sync_primary_store()
        elif not self.stores:
            self.store_id = None

    @property
    def store_names_display(self):
        stores = self.assigned_stores()
        if stores:
            return ", ".join(s.name for s in stores)
        return "—"
