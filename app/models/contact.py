"""Contact-form submissions, surfaced in the admin area (SRS §4.15)."""
from app.extensions import db
from .base import TimestampMixin


class ContactMessage(TimestampMixin, db.Model):
    __tablename__ = "contact_messages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(255))
    subject = db.Column(db.String(80))
    order_number = db.Column(db.String(30))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    reply_text = db.Column(db.Text)
    replied_at = db.Column(db.DateTime(timezone=True))


class Subscriber(db.Model):
    """Newsletter sign-ups from the footer form."""
    __tablename__ = "subscribers"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)
    source = db.Column(db.String(40), default="footer")
    ip_address = db.Column(db.String(45))  # Support IPv6
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    store = db.relationship("Store")
