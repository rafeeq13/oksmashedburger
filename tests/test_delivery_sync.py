"""Uber delivery sync + admin status API — must not 500 on normal paths."""
import pytest
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models.order import Order
from app.models.delivery import Delivery
from app.services.delivery import sync_order_from_delivery, ensure_delivery_status_current


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


def _admin_client(app):
    from app.models.user import User

    c = app.test_client()
    with app.app_context():
        uid = User.query.filter(User.role.has(name="super_admin")).first().id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
    return c


def test_sync_order_from_delivery_transitions(app):
    with app.app_context():
        order = Order.query.filter_by(order_type="delivery").first()
        if not order:
            pytest.skip("no delivery order in database")
        delivery = order.delivery or Delivery(
            order=order, method="uber_direct", status="pending", fee=0
        )
        if not delivery.id:
            db.session.add(delivery)
            db.session.flush()

        order.status = "confirmed"
        delivery.status = "assigned"
        sync_order_from_delivery(delivery)
        assert order.status == "ready"

        delivery.status = "picked_up"
        sync_order_from_delivery(delivery)
        assert order.status == "out_for_delivery"

        delivery.status = "delivered"
        sync_order_from_delivery(delivery)
        assert order.status == "completed"

        db.session.rollback()


def test_sync_skips_terminal_orders(app):
    with app.app_context():
        order = Order.query.filter_by(status="completed").first()
        if not order:
            pytest.skip("no completed order")
        delivery = order.delivery
        if not delivery:
            pytest.skip("completed order has no delivery row")
        prev = order.status
        delivery.status = "assigned"
        assert sync_order_from_delivery(delivery) is False
        assert order.status == prev
        db.session.rollback()


def test_admin_order_status_api_no_500(app):
    c = _admin_client(app)
    with app.app_context():
        order = Order.query.order_by(Order.created_at.desc()).first()
        if not order:
            pytest.skip("no orders")
        number = order.number

    r = c.get(f"/admin/api/orders/{number}/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["number"] == number
    assert "status" in data
    assert "delivery" in data or data.get("delivery") is None


def test_admin_orders_batch_status_empty_ok(app):
    c = _admin_client(app)
    r = c.get("/admin/api/orders/status")
    assert r.status_code == 200
    assert r.get_json() == []


def test_admin_orders_batch_status_with_recent_order(app):
    c = _admin_client(app)
    with app.app_context():
        order = Order.query.order_by(Order.created_at.desc()).first()
        if not order:
            pytest.skip("no orders")
        number = order.number

    r = c.get(f"/admin/api/orders/status?numbers={number}")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    if data:
        assert data[0]["number"] == number


def test_ensure_delivery_status_current_without_delivery(app):
    with app.app_context():
        order = Order.query.filter_by(order_type="pickup").first()
        if not order:
            pytest.skip("no pickup order")
        assert ensure_delivery_status_current(order) is None


def test_tracking_status_poll_no_500(app):
    with app.app_context():
        order = Order.query.order_by(Order.created_at.desc()).first()
        if not order:
            pytest.skip("no orders")
        number = order.number

    c = app.test_client()
    r = c.get(f"/api/orders/{number}/status")
    assert r.status_code == 200
    assert r.get_json().get("status")
