"""Local scratch test: admin menu add/edit/delete + guest checkout order.

    python tools/local_scratch_test.py
"""
import os
import re
import sys
import traceback
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models.menu import Product, Category, StoreMenuItem
from app.models.order import Order
from app.models.store import Store, StoreHours
from app.models.user import User


def csrf(client, path="/"):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else ""


def admin_client(app):
    c = app.test_client()
    with app.app_context():
        uid = User.query.filter(User.role.has(name="super_admin")).first().id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
    return c


def guest_client(app, store_slug, order_type="pickup"):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["store_slug"] = store_slug
        sess["order_type"] = order_type
    return c


def ensure_store_open(store):
    for h in StoreHours.query.filter_by(store_id=store.id).all():
        h.open_time = "00:00"
        h.close_time = "23:59"
    db.session.commit()


def run():
    app = create_app()
    app.config["TESTING"] = True
    errors = []
    product_id = None
    order_number = None

    with app.app_context():
        store = Store.query.filter_by(slug="west-philadelphia", is_active=True).first()
        if not store:
            store = Store.query.filter_by(is_active=True).first()
        if not store:
            print("FAIL: no active store — run: flask --app wsgi seed")
            return 1
        ensure_store_open(store)
        cat = Category.query.order_by(Category.sort_order).first()
        if not cat:
            print("FAIL: no categories — run seed")
            return 1

        qs = "?store=%s" % store.slug
        ac = admin_client(app)
        print("Store:", store.slug, "|", store.name)

        # ── Admin menu page ─────────────────────────────────────────
        try:
            r = ac.get("/admin/menu" + qs)
            assert r.status_code == 200, "menu page %s" % r.status_code
            print("OK  admin menu page")
        except Exception as e:
            errors.append(("admin menu page", e))

        # ── Create catalog item (all locations) ─────────────────────
        try:
            token = csrf(ac, "/admin/menu" + qs)
            r = ac.post(
                "/admin/catalog/products" + qs,
                data={
                    "_csrf": token,
                    "name": "Scratch Test Burger",
                    "category_id": str(cat.id),
                    "base_price": "9.99",
                    "description": "Automated local scratch test item",
                },
                follow_redirects=True,
            )
            assert r.status_code == 200, r.status_code
            product = Product.query.filter_by(name="Scratch Test Burger").order_by(Product.id.desc()).first()
            assert product, "product not created"
            product_id = product.id
            listed = StoreMenuItem.query.filter_by(store_id=store.id, product_id=product_id).first()
            assert listed and listed.is_listed, "not listed on all stores"
            print("OK  created item #%s on all locations" % product_id)
        except Exception as e:
            errors.append(("create item", e))
            traceback.print_exc()

        # ── Store-specific price edit ───────────────────────────────
        if product_id:
            try:
                token = csrf(ac, "/admin/menu" + qs)
                r = ac.post(
                    "/admin/menu/%d%s" % (product_id, qs),
                    data={
                        "_csrf": token,
                        "store": store.slug,
                        "listed": "1",
                        "available": "1",
                        "price": "11.49",
                        "sort_order": "99",
                    },
                    follow_redirects=True,
                )
                assert r.status_code == 200, r.status_code
                mi = StoreMenuItem.query.filter_by(store_id=store.id, product_id=product_id).first()
                assert mi and float(mi.price_override or 0) == 11.49
                other = Store.query.filter(Store.id != store.id, Store.is_active.is_(True)).first()
                if other:
                    mi2 = StoreMenuItem.query.filter_by(store_id=other.id, product_id=product_id).first()
                    assert not mi2 or mi2.price_override is None, "other store price should stay base"
                print("OK  store price override $11.49 at %s only" % store.slug)
            except Exception as e:
                errors.append(("store price edit", e))
                traceback.print_exc()

        # ── Guest order (pickup + cash) ─────────────────────────────
        try:
            product = Product.query.get(product_id) if product_id else Product.query.filter_by(is_active=True).first()
            gc = guest_client(app, store.slug, "pickup")
            token = csrf(gc, "/menu")
            r = gc.post(
                "/cart/add",
                data={
                    "_csrf": token,
                    "product_slug": product.slug,
                    "qty": "1",
                    "next": "/cart",
                },
                follow_redirects=True,
            )
            assert r.status_code == 200, "cart add %s" % r.status_code
            token = csrf(gc, "/checkout")
            r = gc.post(
                "/checkout",
                data={
                    "_csrf": token,
                    "order_type": "pickup",
                    "fulfillment": "asap",
                    "name": "Scratch Test Guest",
                    "email": "scratch-test@example.invalid",
                    "phone": "+12155550199",
                    "payment_method": "cash",
                    "tip": "0",
                    "notes": "Local scratch test order — safe to delete",
                },
                follow_redirects=True,
            )
            assert r.status_code == 200, "checkout %s" % r.status_code
            assert b"order-confirmed" in r.request.path.encode() or b"Order OK-" in r.data or b"placed" in r.data.lower(), (
                "checkout did not confirm: %s" % r.request.path
            )
            order = Order.query.order_by(Order.id.desc()).first()
            assert order and order.customer_name == "Scratch Test Guest"
            order_number = order.number
            print("OK  placed order %s total $%s (%s)" % (order.number, order.total, order.payment_method))
        except Exception as e:
            errors.append(("checkout order", e))
            traceback.print_exc()

        # ── Delete test item ────────────────────────────────────────
        if product_id:
            try:
                token = csrf(ac, "/admin/menu/%d/edit%s" % (product_id, qs))
                r = ac.post(
                    "/admin/menu/%d/delete%s" % (product_id, qs),
                    data={"_csrf": token},
                    follow_redirects=True,
                )
                assert r.status_code == 200, r.status_code
                assert Product.query.get(product_id) is None
                print("OK  deleted scratch test item")
            except Exception as e:
                errors.append(("delete item", e))
                traceback.print_exc()

        print("\n" + "=" * 50)
        if errors:
            print("FAILED %d step(s):" % len(errors))
            for name, err in errors:
                print(" - %s: %s" % (name, err))
            return 1
        print("ALL PASSED")
        if order_number:
            print("Test order %s left in admin -> Orders (cash/pending)." % order_number)
        return 0


if __name__ == "__main__":
    raise SystemExit(run())
