"""Saved delivery addresses for signed-in customers (SRS §4.3)."""
from app.extensions import db
from .base import TimestampMixin


class UserAddress(TimestampMixin, db.Model):
    __tablename__ = "user_addresses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=False)
    label = db.Column(db.String(40), default="Home")       # Home / Work / …
    recipient = db.Column(db.String(120))
    line1 = db.Column(db.String(255), nullable=False)
    line2 = db.Column(db.String(120))
    city = db.Column(db.String(80), default="Philadelphia")
    state = db.Column(db.String(40), default="PA")
    zip_code = db.Column(db.String(12))
    phone = db.Column(db.String(40))
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", backref=db.backref("addresses", cascade="all, delete-orphan"))

    @property
    def one_line(self):
        parts = [self.line1]
        if self.line2:
            parts.append(self.line2)
        parts.append(f"{self.city}, {self.state} {self.zip_code}".strip())
        return ", ".join(p for p in parts if p)
