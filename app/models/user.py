"""Users & Role-Based Access Control (SRS §2.3, §4.1)."""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.extensions import db
from .base import TimestampMixin

_ph = PasswordHasher()

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

    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    role = db.relationship("Role", back_populates="users")

    # Staff are scoped to a store (nullable for corporate / customers)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"))
    store = db.relationship("Store")

    loyalty_points = db.Column(db.Integer, default=0, nullable=False)

    def set_password(self, raw):
        self.password_hash = _ph.hash(raw)

    def check_password(self, raw):
        try:
            return _ph.verify(self.password_hash, raw)
        except VerifyMismatchError:
            return False

    @property
    def full_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.email
