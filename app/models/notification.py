"""Order notifications log — one row per message a store sends about an order.

Which channel fires depends on the STORE's own integrations (Twilio for SMS,
SendGrid for email), so two locations can notify differently. In demo mode the
send is simulated and recorded here with status="simulated" (SRS §5.2, FR-10)."""
from app.extensions import db
from .base import TimestampMixin

NOTIFY_CHANNELS = ["sms", "email"]
NOTIFY_STATUSES = ["simulated", "sent", "failed", "skipped"]


class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), index=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), index=True)
    channel = db.Column(db.String(10), nullable=False)      # sms / email
    provider = db.Column(db.String(20), nullable=False)     # twilio / sendgrid
    recipient = db.Column(db.String(255), nullable=False)   # phone or email
    subject = db.Column(db.String(160))                     # email only
    body = db.Column(db.Text, nullable=False)
    event = db.Column(db.String(30), nullable=False)        # order status that triggered it
    status = db.Column(db.String(20), default="simulated", nullable=False)
    provider_ref = db.Column(db.String(120))

    order = db.relationship("Order", backref="notifications")
    store = db.relationship("Store")
