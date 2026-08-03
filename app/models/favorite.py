"""Customer favorites — products a signed-in user saved for faster reordering."""
from app.extensions import db
from .base import TimestampMixin


class Favorite(TimestampMixin, db.Model):
    __tablename__ = "favorites"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), index=True, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),)

    user = db.relationship("User", backref=db.backref("favorites", cascade="all, delete-orphan"))
    product = db.relationship("Product")
