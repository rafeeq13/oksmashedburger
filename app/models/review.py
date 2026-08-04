"""Customer-submitted reviews.

Kept separate from ContentItem's curated `testimonials` list on purpose: those
are marketing copy the client writes, these arrive from the public and must be
moderated before anyone sees them. Nothing a visitor submits is ever shown
until a manager approves it — an unmoderated public feed on a restaurant site
is a spam magnet and a reputational risk.

The two sources are merged for display in `content_list_reviews()`.
"""
from app.extensions import db
from .base import TimestampMixin

REVIEW_STATUSES = ("pending", "approved", "rejected")


class Review(TimestampMixin, db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)

    # who wrote it — display name is shown, email never is
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    rating = db.Column(db.Integer, nullable=False, default=5)   # 1-5
    body = db.Column(db.Text, nullable=False)

    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), index=True)
    order_number = db.Column(db.String(30))                     # optional proof of purchase

    status = db.Column(db.String(12), default="pending", nullable=False, index=True)
    moderated_at = db.Column(db.DateTime)
    moderated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    user = db.relationship("User", foreign_keys=[user_id])
    store = db.relationship("Store")
    moderated_by = db.relationship("User", foreign_keys=[moderated_by_id])

    @property
    def display_name(self):
        """"Jordan Miller" is shown as "Jordan M." — first name plus an
        initial, the convention the seeded reviews already use."""
        parts = (self.name or "").strip().split()
        if not parts:
            return "Guest"
        if len(parts) == 1:
            return parts[0]
        return "%s %s." % (parts[0], parts[-1][0].upper())

    @property
    def age_label(self):
        """"2 weeks ago" style, to sit alongside the curated entries."""
        from datetime import datetime, timezone
        if not self.created_at:
            return ""
        now = datetime.now(timezone.utc)
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days = max(0, (now - created).days)
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return "%d days ago" % days
        if days < 30:
            weeks = days // 7
            return "%d week%s ago" % (weeks, "" if weeks == 1 else "s")
        if days < 365:
            months = days // 30
            return "%d month%s ago" % (months, "" if months == 1 else "s")
        years = days // 365
        return "%d year%s ago" % (years, "" if years == 1 else "s")

    def as_card(self):
        """Same shape the curated testimonials use, so one template renders both."""
        return {"name": self.display_name, "when": self.age_label,
                "stars": self.rating, "text": self.body, "_review_id": self.id}


def approved_reviews(limit=24):
    return (Review.query.filter_by(status="approved")
            .order_by(Review.created_at.desc()).limit(limit).all())


def pending_count():
    return Review.query.filter_by(status="pending").count()
