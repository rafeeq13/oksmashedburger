import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.models.store import Store
from app.integrations.config import active_integration_config, should_simulate
from app.integrations import uber_gateway

app = create_app()
with app.app_context():
    s = Store.query.filter_by(slug="west-philadelphia").first()
    cfg = active_integration_config(s, "uber_direct")
    print("uber enabled", uber_gateway.is_enabled(s), "simulate", should_simulate(s, "uber_direct"))
    r = requests.post(
        "https://auth.uber.com/oauth/v2/token",
        data={
            "client_id": cfg.get("client_id", "").strip(),
            "client_secret": cfg.get("client_secret", "").strip(),
            "grant_type": "client_credentials",
            "scope": "eats.deliveries",
        },
        timeout=20,
    )
    print("status", r.status_code)
    if r.ok:
        print("uber oauth: OK")
    else:
        print("uber oauth FAIL:", r.text[:200])
