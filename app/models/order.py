"""Orders, order items and payments (SRS §4.6, §4.5)."""
from app.extensions import db
from .base import TimestampMixin

ORDER_STATUSES = ["placed", "confirmed", "preparing", "ready", "out_for_delivery", "completed", "cancelled"]


class Order(TimestampMixin, db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), unique=True, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))          # null for guest checkout
    status = db.Column(db.String(30), default="placed", nullable=False)
    order_type = db.Column(db.String(20), default="delivery")           # delivery / pickup
    scheduled_for = db.Column(db.DateTime(timezone=True))               # null = ASAP; set = order-ahead

    customer_name = db.Column(db.String(160))
    customer_email = db.Column(db.String(255))
    customer_phone = db.Column(db.String(40))
    address = db.Column(db.String(400))
    notes = db.Column(db.Text)

    subtotal = db.Column(db.Numeric(10, 2), default=0)
    tax = db.Column(db.Numeric(10, 2), default=0)
    delivery_fee = db.Column(db.Numeric(10, 2), default=0)
    tip = db.Column(db.Numeric(10, 2), default=0)
    discount = db.Column(db.Numeric(10, 2), default=0)
    coupon_code = db.Column(db.String(40))
    points_redeemed = db.Column(db.Integer, default=0)
    gift_card_applied = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), default=0)
    currency = db.Column(db.String(3), default="USD")

    payment_status = db.Column(db.String(20), default="pending")        # pending / paid / failed
    payment_method = db.Column(db.String(20))                           # card / cash

    store = db.relationship("Store")
    user = db.relationship("User")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payment = db.relationship("Payment", back_populates="order", uselist=False, cascade="all, delete-orphan")

    @property
    def item_count(self):
        return sum(i.qty for i in self.items)


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    name = db.Column(db.String(200), nullable=False)         # snapshot at purchase time
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    qty = db.Column(db.Integer, default=1, nullable=False)
    options = db.Column(db.JSON, default=dict)               # {variant, addons, notes}
    line_total = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    provider = db.Column(db.String(30), default="stripe")   # stripe / cash / square
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default="USD")
    status = db.Column(db.String(20), default="pending")    # pending / succeeded / failed
    provider_ref = db.Column(db.String(160))                # e.g. Stripe PaymentIntent id (per store)
    raw = db.Column(db.JSON, default=dict)

    order = db.relationship("Order", back_populates="payment")
