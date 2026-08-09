"""Coupons/promotions + gift cards (SRS §4.9)."""
from datetime import datetime, timezone

from app.extensions import db
from .base import TimestampMixin

COUPON_KINDS = ["percent", "fixed", "free_delivery"]


class Coupon(TimestampMixin, db.Model):
    __tablename__ = "coupons"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, index=True, nullable=False)
    kind = db.Column(db.String(20), nullable=False)          # percent / fixed / free_delivery
    value = db.Column(db.Numeric(8, 2), default=0)           # % for percent, $ for fixed
    min_order = db.Column(db.Numeric(8, 2), default=0)
    requires_code = db.Column(db.Boolean, default=True, nullable=False)  # False = auto deal, no code needed
    active = db.Column(db.Boolean, default=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True))
    max_uses = db.Column(db.Integer)                         # null = unlimited
    used_count = db.Column(db.Integer, default=0, nullable=False)
    description = db.Column(db.String(200))
    image_url = db.Column(db.String(400))   # the photo on the deal card, set from the admin

    def validate(self, subtotal):
        """Return (ok, error_message)."""
        if not self.active:
            return False, "This code is no longer active."
        if self.expires_at:
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                return False, "This code has expired."
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False, "This code has reached its usage limit."
        if float(subtotal) < float(self.min_order):
            return False, f"Add ${float(self.min_order) - float(subtotal):.2f} more to use this code."
        return True, None

    def compute(self, subtotal, delivery_fee):
        """Return dict {order_discount, delivery_discount}."""
        if self.kind == "percent":
            return {"order_discount": round(float(subtotal) * float(self.value) / 100.0, 2), "delivery_discount": 0.0}
        if self.kind == "fixed":
            return {"order_discount": min(float(self.value), float(subtotal)), "delivery_discount": 0.0}
        if self.kind == "free_delivery":
            return {"order_discount": 0.0, "delivery_discount": float(delivery_fee)}
        return {"order_discount": 0.0, "delivery_discount": 0.0}


class GiftCard(TimestampMixin, db.Model):
    __tablename__ = "gift_cards"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, index=True, nullable=False)
    initial_balance = db.Column(db.Numeric(8, 2), nullable=False)
    balance = db.Column(db.Numeric(8, 2), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    recipient_email = db.Column(db.String(255))
    sender_name = db.Column(db.String(120))
    message = db.Column(db.String(255))
