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


class Subscriber(db.Model):
    """Newsletter sign-ups from the footer form."""
    __tablename__ = "subscribers"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    source = db.Column(db.String(40), default="footer")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
