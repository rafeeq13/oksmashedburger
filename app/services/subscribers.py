"""Newsletter subscriber list — shared by footer sign-up and checkout."""
from app.extensions import db
from app.models.contact import Subscriber


def _valid_email(email):
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return ""
    if "." not in email.split("@")[-1]:
        return ""
    return email


def ensure_subscriber(email, store=None, source="order", ip_address=None, send_welcome=False):
    """Add or reactivate a subscriber. Returns the row or None if email invalid.

    Welcome email is sent by the caller after commit (see /subscribe), not here.
    send_welcome is ignored (kept for call-site compatibility).
    """
    email = _valid_email(email)
    if not email:
        return None

    existing = Subscriber.query.filter_by(email=email).first()
    if existing:
        existing.is_active = True
        if store and store.id:
            existing.store_id = store.id
        if source:
            existing.source = (source or existing.source or "order")[:40]
        if ip_address:
            existing.ip_address = ip_address
        return existing

    row = Subscriber(
        email=email,
        source=(source or "order")[:40],
        store_id=store.id if store else None,
        ip_address=ip_address,
        is_active=True,
    )
    db.session.add(row)
    return row
