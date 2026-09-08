import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.models.store import Store

app = create_app()
with app.app_context():
    for s in Store.query.filter_by(is_active=True).order_by(Store.name):
        try:
            on = s.open_now
        except Exception as e:
            on = "ERROR: %s" % e
        print(s.slug, "accepting=", s.accepting_orders, "scheduled=", s.accepting_scheduled, "open_now=", on, "hours_rows=", len(s.hours))
