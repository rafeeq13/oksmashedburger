"""Remove sandbox customer/transactional data before production launch."""
from app.models.user import Role, User
from app.models.notification import Notification
from app.models.contact import Subscriber, ContactMessage
from app.models.order import Order, OrderItem, Payment
from app.models.delivery import Delivery
from app.models.review import Review
from app.models.favorite import Favorite
from app.models.address import UserAddress
from app.models.payment_method import UserPaymentMethod
from app.extensions import db

STAFF_ROLES = (
    "super_admin", "franchise_owner", "store_manager",
    "kitchen_staff", "cashier", "driver",
)
CUSTOMER_ROLES = ("customer", "guest")


def clean_test_data():
    counts = {}

    counts["notifications"] = Notification.query.delete()
    counts["deliveries"] = Delivery.query.delete()
    counts["payments"] = Payment.query.delete()
    counts["order_items"] = OrderItem.query.delete()
    counts["orders"] = Order.query.delete()
    counts["reviews"] = Review.query.delete()

    customer_role_ids = [
        r.id for r in Role.query.filter(Role.name.in_(CUSTOMER_ROLES)).all()
    ]
    customer_ids = []
    if customer_role_ids:
        customer_ids = [
            row[0] for row in User.query.filter(User.role_id.in_(customer_role_ids))
            .with_entities(User.id).all()
        ]
    if customer_ids:
        counts["favorites"] = Favorite.query.filter(
            Favorite.user_id.in_(customer_ids)
        ).delete(synchronize_session=False)
        counts["user_addresses"] = UserAddress.query.filter(
            UserAddress.user_id.in_(customer_ids)
        ).delete(synchronize_session=False)
        counts["user_payment_methods"] = UserPaymentMethod.query.filter(
            UserPaymentMethod.user_id.in_(customer_ids)
        ).delete(synchronize_session=False)
        counts["customers"] = User.query.filter(
            User.id.in_(customer_ids)
        ).delete(synchronize_session=False)
    else:
        counts["customers"] = 0

    counts["subscribers"] = Subscriber.query.delete()
    counts["contact_messages"] = ContactMessage.query.delete()

    db.session.commit()
    return counts
