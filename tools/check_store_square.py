import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.store import Store
from app.integrations.config import active_integration_config, integration_env
from app.integrations import square_gateway
from app.integrations.square_gateway import _request


def main():
    app = create_app()
    with app.app_context():
        s = Store.query.filter_by(slug="northeast-philadelphia").first()
        if not s:
            print("ERROR: store not found")
            return 1

        cfg = active_integration_config(s, "square")
        loc = (cfg.get("location_id") or "").strip()
        app_id = (cfg.get("application_id") or "").strip()
        tok = (cfg.get("access_token") or "").strip()

        print("=== NORTHEAST PHILADELPHIA (7014 Frankford) ===")
        print("integration_env:", integration_env(s))
        print("square enabled:", square_gateway.is_enabled(s))
        print("application_id:", app_id[:28] + "..." if len(app_id) > 28 else app_id or "(empty)")
        print("location_id:", loc or "(empty)")
        print("access_token:", (tok[:8] + "..." + tok[-4:]) if len(tok) > 12 else ("(empty)" if not tok else "(set)"))

        issues = []
        if loc.startswith("sandbox-sq0idb") or loc.startswith("sq0idb-"):
            issues.append("location_id is Application ID - must be L… Location ID")
        elif not loc.startswith("L"):
            issues.append("location_id should start with L")
        if not tok:
            issues.append("access_token missing")
        if not app_id:
            issues.append("application_id missing (optional but recommended)")

        if issues:
            print("\nISSUES:")
            for i in issues:
                print(" -", i)
        else:
            print("\nConfig looks valid.")

        print("\n=== SQUARE API: LIST LOCATIONS ===")
        resp = _request(s, "GET", "/v2/locations")
        if resp.get("errors"):
            print("API ERROR:", resp.get("errors"))
            return 2
        locations = resp.get("locations") or []
        if not locations:
            print("No locations returned")
            return 2

        match = None
        for item in locations:
            addr = item.get("address") or {}
            line = addr.get("address_line_1") or ""
            print(
                " ",
                item.get("id"),
                "|",
                item.get("name"),
                "|",
                line,
                addr.get("postal_code") or "",
                "|",
                item.get("status"),
            )
            if loc and item.get("id") == loc:
                match = item
            if "7014" in line or "Frankford" in line:
                print("   ^ matches 7014 Frankford area")

        print("\n=== LOCATION ID CHECK ===")
        if loc:
            detail = _request(s, "GET", "/v2/locations/" + loc)
            if detail.get("errors"):
                print("GET /locations/" + loc + " ERROR:", detail.get("errors"))
            elif detail.get("location"):
                item = detail["location"]
                addr = item.get("address") or {}
                print("OK: location_id valid in Square API")
                print("  name:", item.get("name"))
                print("  address:", addr.get("address_line_1"), addr.get("locality"), addr.get("postal_code"))
                match = item
            else:
                print("GET location response:", detail)

        if match:
            addr = match.get("address") or {}
            print("OK: configured location_id exists in Square")
            print("  name:", match.get("name"))
            print("  address:", addr.get("address_line_1"), addr.get("locality"), addr.get("postal_code"))
        elif loc:
            print("WARN: location_id", loc, "not found in token's location list")
            print("  Use one of the IDs above, or create 7014 Frankford in Square Dashboard")

        return 0 if square_gateway.is_enabled(s) and match and not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
