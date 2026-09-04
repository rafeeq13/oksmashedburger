"""Inbound webhook log | one row per provider callback."""
from app.extensions import db
from .base import TimestampMixin


class WebhookEvent(TimestampMixin, db.Model):
    __tablename__ = "webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), index=True)
    provider = db.Column(db.String(30), nullable=False, index=True)
    event_type = db.Column(db.String(120), nullable=False)
    external_id = db.Column(db.String(160), index=True)
    status = db.Column(db.String(20), default="received", nullable=False)  # received/processed/ignored/failed
    payload = db.Column(db.JSON, default=dict)
    error = db.Column(db.Text)

    store = db.relationship("Store")
