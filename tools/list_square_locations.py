"""List Square sandbox locations for the configured access token."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.integrations.config import active_integration_config
from app.integrations.square_gateway import _request, store_square_config


def main():
    app = create_app()
    with app.app_context():
        store = Store.query.filter_by(slug="south-snyder").first()
        cfg = active_integration_config(store, "square")
        print("current location_id:", cfg.get("location_id"))
        print("application_id:", cfg.get("application_id"))
        resp = _request(store, "GET", "/v2/locations")
        print(json.dumps(resp, indent=2)[:4000])


if __name__ == "__main__":
    main()
