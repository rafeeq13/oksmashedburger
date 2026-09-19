"""Newsletter subscriber helpers."""
import pytest
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models.contact import Subscriber
from app.services.subscribers import ensure_subscriber


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


def test_ensure_subscriber_creates_order_source(app):
    with app.app_context():
        email = "order-test@example.com"
        Subscriber.query.filter_by(email=email).delete()
        db.session.commit()

        row = ensure_subscriber(email, source="order")
        db.session.commit()
        assert row is not None
        assert row.source == "order"
        assert row.is_active is True

        Subscriber.query.filter_by(email=email).delete()
        db.session.commit()


def test_ensure_subscriber_reactivates_existing(app):
    with app.app_context():
        email = "reactivate-test@example.com"
        Subscriber.query.filter_by(email=email).delete()
        db.session.add(Subscriber(email=email, source="footer", is_active=False))
        db.session.commit()

        row = ensure_subscriber(email, source="order")
        db.session.commit()
        assert row.is_active is True
        assert row.source == "order"

        Subscriber.query.filter_by(email=email).delete()
        db.session.commit()
