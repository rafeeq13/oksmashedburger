"""Full admin menu CRUD: add, image upload, edit fields/photo/price, delete.

    python tools/local_menu_full_test.py
"""
import os
import re
import sys
import traceback
from decimal import Decimal
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models.menu import Product, Category, StoreMenuItem
from app.models.store import Store
from app.models.user import User

# 1x1 red PNG
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PNG_1X1_BLUE = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def png_file(data, name):
    return (BytesIO(data), name)


def run():
    app = create_app()
    app.config["TESTING"] = True
    errors = []
    product_id = None
    first_image = None
    second_image = None

    with app.app_context():
        store = Store.query.filter_by(slug="south-snyder", is_active=True).first()
        if not store:
            store = Store.query.filter_by(is_active=True).first()
        cat = Category.query.order_by(Category.sort_order).first()
        if not store or not cat:
            print("FAIL: seed database first (flask --app wsgi seed)")
            return 1

        qs = "?store=%s" % store.slug
        ac = admin_client(app)
        print("Location:", store.slug)

        # ── 1. Create with image upload ─────────────────────────────
        try:
            token = csrf(ac, "/admin/menu" + qs)
            r = ac.post(
                "/admin/catalog/products" + qs,
                data={
                    "_csrf": token,
                    "name": "Full Edit Test Burger",
                    "category_id": str(cat.id),
                    "base_price": "8.50",
                    "description": "First description for full menu test",
                    "calories": "650",
                    "allergens": "gluten, dairy",
                    "tags": "test, scratch",
                    "sort_order": "50",
                    "image_file": png_file(PNG_1X1, "full-edit-test.png"),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            assert r.status_code == 200, r.status_code
            product = Product.query.filter_by(name="Full Edit Test Burger").order_by(Product.id.desc()).first()
            assert product, "product missing after create"
            product_id = product.id
            assert product.image_url and "/static/img/uploads/" in product.image_url
            first_image = product.image_url
            upload_path = os.path.join(
                app.static_folder, "img", "uploads",
                os.path.basename(product.image_url),
            )
            assert os.path.isfile(upload_path), "uploaded file not on disk: %s" % upload_path
            assert StoreMenuItem.query.filter_by(store_id=store.id, product_id=product_id).count() == 1
            print("OK  created item #%s with image %s" % (product_id, os.path.basename(first_image)))
        except Exception as e:
            errors.append(("create + image", e))
            traceback.print_exc()

        if not product_id:
            _report(errors)
            return 1

        # ── 2. Menu list: store price + listed/available ────────────
        try:
            token = csrf(ac, "/admin/menu" + qs)
            r = ac.post(
                "/admin/menu/%d%s" % (product_id, qs),
                data={
                    "_csrf": token,
                    "store": store.slug,
                    "listed": "1",
                    "available": "1",
                    "price": "9.25",
                    "sort_order": "51",
                },
                follow_redirects=True,
            )
            assert r.status_code == 200
            mi = StoreMenuItem.query.filter_by(store_id=store.id, product_id=product_id).first()
            assert mi and float(mi.price_override or 0) == 9.25
            assert mi.is_listed and mi.is_available
            print("OK  menu list save: store price $9.25, listed, available")
        except Exception as e:
            errors.append(("menu list price", e))
            traceback.print_exc()

        # ── 3. Full edit page: name, description, photo, store price ─
        try:
            token = csrf(ac, "/admin/menu/%d/edit%s" % (product_id, qs))
            r = ac.post(
                "/admin/menu/%d/edit%s" % (product_id, qs),
                data={
                    "_csrf": token,
                    "name": "Full Edit Test Burger XL",
                    "category_id": str(cat.id),
                    "base_price": "10.75",
                    "description": "Updated description after photo swap",
                    "calories": "720",
                    "allergens": "gluten",
                    "tags": "test, updated",
                    "sort_order": "52",
                    "is_vegan": "1",
                    "is_active": "1",
                    "image_file": png_file(PNG_1X1_BLUE, "full-edit-test-v2.png"),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            assert r.status_code == 200
            db.session.expire_all()
            product = db.session.get(Product, product_id)
            assert product.name == "Full Edit Test Burger XL"
            assert product.description == "Updated description after photo swap"
            assert product.calories == 720
            assert product.is_vegan
            assert product.image_url and "/static/img/uploads/" in product.image_url
            second_image = product.image_url
            upload_path = os.path.join(app.static_folder, "img", "uploads", os.path.basename(second_image))
            assert os.path.isfile(upload_path), "new image missing on disk"
            with open(upload_path, "rb") as fh:
                on_disk = fh.read()
            assert on_disk == PNG_1X1_BLUE, "photo file should be replaced on re-upload"
            mi = StoreMenuItem.query.filter_by(store_id=store.id, product_id=product_id).first()
            assert float(mi.price_override or 0) == 10.75
            assert float(product.base_price) == 8.50, "catalog base should stay when store selected"
            print("OK  full edit: name, description, vegan, new photo, store price $10.75")
        except Exception as e:
            errors.append(("full edit + photo", e))
            traceback.print_exc()

        # ── 4. Edit page renders with new data ────────────────────
        try:
            r = ac.get("/admin/menu/%d/edit%s" % (product_id, qs))
            html = r.get_data(as_text=True)
            assert r.status_code == 200
            assert "Full Edit Test Burger XL" in html
            assert "Updated description after photo swap" in html
            assert second_image and (second_image in html or os.path.basename(second_image) in html)
            print("OK  edit page shows updated fields and image")
        except Exception as e:
            errors.append(("edit page render", e))
            traceback.print_exc()

        # ── 5. Delete item ────────────────────────────────────────
        try:
            token = csrf(ac, "/admin/menu/%d/edit%s" % (product_id, qs))
            r = ac.post(
                "/admin/menu/%d/delete%s" % (product_id, qs),
                data={"_csrf": token},
                follow_redirects=True,
            )
            assert r.status_code == 200
            assert db.session.get(Product, product_id) is None
            print("OK  deleted item #%s" % product_id)
        except Exception as e:
            errors.append(("delete", e))
            traceback.print_exc()

    return _report(errors)


def _report(errors):
    print("\n" + "=" * 50)
    if errors:
        print("FAILED %d step(s):" % len(errors))
        for name, err in errors:
            print(" - %s: %s" % (name, err))
        return 1
    print("ALL PASSED — full menu CRUD with images")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
