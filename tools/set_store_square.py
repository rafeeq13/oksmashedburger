"""Set Square sandbox credentials for a store (run on server with env vars).

Usage:
  SQUARE_TOKEN=... python tools/set_store_square.py northeast-philadelphia \\
    --application-id sandbox-sq0idb-... --location-id LNBGJEQDP0WTF
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.store import Store, StoreIntegration
from app.integrations.config import integration_env, merge_env_config, active_integration_config
from app.integrations import square_gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("store_slug")
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--location-id", required=True)
    parser.add_argument("--token", default=os.environ.get("SQUARE_TOKEN", ""))
    args = parser.parse_args()

    if not args.token:
        print("ERROR: set SQUARE_TOKEN env or pass --token")
        return 1
    if args.location_id.startswith("sandbox-sq0idb"):
        print("ERROR: location_id must start with L, not Application ID")
        return 1

    app = create_app()
    with app.app_context():
        store = Store.query.filter_by(slug=args.store_slug, is_active=True).first()
        if not store:
            print("ERROR: store not found:", args.store_slug)
            return 1

        integ = StoreIntegration.query.filter_by(store_id=store.id, provider="square").first()
        if not integ:
            integ = StoreIntegration(store_id=store.id, provider="square", enabled=True, config={})
            db.session.add(integ)

        integ.enabled = True
        env = integration_env(store)
        bucket = dict(active_integration_config(store, "square"))
        bucket["application_id"] = args.application_id.strip()
        bucket["location_id"] = args.location_id.strip()
        bucket["access_token"] = args.token.strip()
        merge_env_config(integ, env, bucket)
        db.session.commit()

        print("OK:", store.slug, "| env:", env)
        print("  application_id:", bucket["application_id"][:30] + "...")
        print("  location_id:", bucket["location_id"])
        print("  square enabled:", square_gateway.is_enabled(store))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
