"""Extra live checks: Uber token, menu, store hours."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.models.menu import StoreMenuItem
from app.integrations import uber_gateway, smtp_gateway
from app.integrations.config import active_integration_config, should_simulate, integration_enabled


def main():
    app = create_app()
    with app.app_context():
        stores = Store.query.filter_by(is_active=True).order_by(Store.name).all()
        print("=== EXTRA LIVE CHECKS ===\n")
        for s in stores:
            print(s.name, "(%s)" % s.slug)
            listed = StoreMenuItem.query.filter_by(
                store_id=s.id, is_listed=True, is_available=True
            ).count()
            zones = len(s.delivery_zones or [])
            print("  menu listed:", listed, "| delivery zones:", zones)
            from datetime import datetime
            print("  accepting_orders:", s.accepting_orders, "| open_now:", s.is_open_at(datetime.now()))
            print("  pickup:", getattr(s, "pickup_enabled", True), "| delivery:", getattr(s, "delivery_enabled", True))
            if uber_gateway.is_enabled(s) and not should_simulate(s, "uber_direct"):
                try:
                    import requests
                    cfg = active_integration_config(s, "uber_direct")
                    cid = cfg.get("client_id", "").strip()
                    secret = cfg.get("client_secret", "").strip()
                    r = requests.post(
                        "https://auth.uber.com/oauth/v2/token",
                        data={"client_id": cid, "client_secret": secret, "grant_type": "client_credentials", "scope": "eats.deliveries"},
                        timeout=15,
                    )
                    ok = r.status_code == 200 and bool(r.json().get("access_token"))
                    print("  uber oauth:", "OK" if ok else "FAIL %s %s" % (r.status_code, r.text[:120]))
                except Exception as exc:
                    print("  uber oauth: ERROR", exc)
            smtp_cfg = active_integration_config(s, "smtp")
            print("  smtp:", smtp_gateway.is_enabled(s), smtp_cfg.get("from_email", ""))
            gm = active_integration_config(s, "google_maps")
            print("  maps key:", "set" if gm.get("api_key") else "MISSING")
            print()


if __name__ == "__main__":
    main()
