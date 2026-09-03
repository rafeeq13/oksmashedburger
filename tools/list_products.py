import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.menu import Product

app = create_app()
with app.app_context():
    for p in Product.query.filter_by(is_active=True).order_by(Product.id).all():
        print(f"{p.slug} | {p.name} | {p.base_price}")
