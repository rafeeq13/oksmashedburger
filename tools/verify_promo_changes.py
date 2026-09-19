"""Quick smoke check for promo/subscribe changes (run from repo root)."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
db = os.path.join(ROOT, "instance", "dev.db").replace("\\", "/")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{db}")

from app import create_app
from app.services.promo_banners import normalize_promo_banner


def main():
    app = create_app()
    legacy = normalize_promo_banner(
        {"enabled": True, "placement": "visit_popup", "show_subscribe": True}
    )
    assert legacy["popup_email_width_pct"] == 74
    assert legacy["popup_subscribe_join_bg"] is True
    assert legacy["show_deals_link"] is True

    errors = []
    with app.test_client() as c:
        for path in ("/", "/deals"):
            r = c.get(path)
            if r.status_code != 200:
                errors.append(f"GET {path} -> {r.status_code}")

        r0 = c.get("/")
        html = r0.get_data(as_text=True)
        if "okDealsPromoPopup" not in html and legacy.get("enabled"):
            # popup may be hidden by visibility rules; not a 500
            pass

        m = re.search(r'name="_csrf" value="([^"]+)"', html)
        if not m:
            errors.append("CSRF token missing on home")
        else:
            r = c.post(
                "/subscribe",
                data={
                    "_csrf": m.group(1),
                    "email": "verify-promo-smoke@example.invalid",
                    "source": "promo_banner",
                    "redirect": "/deals",
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if r.status_code != 200:
                errors.append(f"POST /subscribe -> {r.status_code} {r.get_data(as_text=True)[:200]}")
            else:
                data = r.get_json()
                if not data or not data.get("ok"):
                    errors.append(f"subscribe JSON not ok: {data}")
                if data.get("redirect") != "/deals":
                    errors.append(f"subscribe redirect missing: {data}")

        r = c.get("/admin/promo-banner", follow_redirects=False)
        if r.status_code not in (200, 302):
            errors.append(f"GET /admin/promo-banner -> {r.status_code}")

    js = open(os.path.join(ROOT, "app", "static", "js", "app.js"), encoding="utf-8").read()
    for needle in (
        "flushPromoSubscribeToast",
        "okDealsPromoShouldSkip",
        "okPromoSubscribeToast",
    ):
        if needle not in js:
            errors.append(f"app.js missing {needle}")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("OK: promo/subscribe smoke checks passed")


if __name__ == "__main__":
    main()
