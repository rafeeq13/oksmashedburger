"""Saved payment methods for customer accounts."""
from app.extensions import db


class UserPaymentMethod(db.Model):
    __tablename__ = "user_payment_methods"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    brand = db.Column(db.String(20), default="Card")          # Visa, Mastercard, …
    last4 = db.Column(db.String(4), nullable=False)
    exp_month = db.Column(db.String(2))
    exp_year = db.Column(db.String(4))
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", backref=db.backref("payment_methods", cascade="all, delete-orphan"))

    @property
    def display(self):
        return f"{self.brand} •••• {self.last4}"
