import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app import cart as cartlib
from app.models.menu import Product


def main():
    app = create_app()
    with app.app_context():
        c = app.test_client()
        product = Product.query.filter_by(is_active=True).first()
        with c.session_transaction() as sess:
            sess["store_slug"] = "north-philadelphia"
            sess["cart"] = [{
                "product_id": product.id,
                "slug": product.slug,
                "name": product.name,
                "image": product.image_url,
                "unit_price": float(product.base_price),
                "qty": 1,
                "options": {},
            }]
        html = c.get("/checkout").data.decode("utf-8", "replace")
        m = re.search(r'name="_csrf" value="([^"]+)"', html)
        token = m.group(1) if m else ""
        r = c.post(
            "/checkout/payment-intent",
            json={"amount": 25.50},
            headers={"X-CSRF-Token": token},
        )
        print("payment-intent", r.status_code, r.get_json())
        print("stripe.js", "js.stripe.com" in html)
        print("card-element", "card-element" in html)
        data = r.get_json() or {}
        return 0 if r.status_code == 200 and data.get("ok") and data.get("client_secret") else 1


if __name__ == "__main__":
    raise SystemExit(main())
