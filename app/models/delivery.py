"""Delivery: own-fleet drivers + dispatched deliveries (SRS §4.8)."""
from app.extensions import db
from .base import TimestampMixin

DELIVERY_STATUSES = ["pending", "assigned", "picked_up", "delivered", "failed"]


class Driver(TimestampMixin, db.Model):
    __tablename__ = "drivers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    vehicle = db.Column(db.String(120))
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))   # optional login for the driver app
    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=True)

    store = db.relationship("Store")
    user = db.relationship("User")
    deliveries = db.relationship("Delivery", back_populates="driver")


class Delivery(TimestampMixin, db.Model):
    __tablename__ = "deliveries"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False)
    method = db.Column(db.String(20), default="own")            # own / uber_direct
    status = db.Column(db.String(20), default="pending")        # see DELIVERY_STATUSES
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"))
    provider_ref = db.Column(db.String(160))                    # Uber Direct delivery id
    tracking_url = db.Column(db.String(500))
    fee = db.Column(db.Numeric(8, 2), default=0)
    proof = db.Column(db.String(255))                           # proof-of-delivery note
    assigned_at = db.Column(db.DateTime(timezone=True))
    picked_up_at = db.Column(db.DateTime(timezone=True))
    delivered_at = db.Column(db.DateTime(timezone=True))

    order = db.relationship("Order", backref=db.backref("delivery", uselist=False))
    driver = db.relationship("Driver", back_populates="deliveries")
