"""Smoke-test pages that render promo banner / CTA."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()
client = app.test_client()
routes = [
    "/",
    "/menu",
    "/deals",
    "/contact",
    "/set-location/south-washington?next=/menu",
    "/menu?edit=1",
    "/deals?edit=1",
]
fail = []
for path in routes:
    r = client.get(path, follow_redirects=True)
    if r.status_code >= 500:
        fail.append((path, r.status_code))
    elif b"Traceback" in r.data or b"Internal Server Error" in r.data:
        fail.append((path, "body_error"))
    else:
        print("OK", r.status_code, path, "bytes", len(r.data))

from app.services.promo_banners import load_promo_banner, promo_banner_visible
from app.models.store import Store

from app.services.promo_banners import normalize_promo_banner

with app.app_context():
    s = Store.query.filter_by(is_active=True).first()
    cfg = load_promo_banner(s)
    vis = promo_banner_visible(cfg, {}, "/menu", inline_edit=False)
    print("promo visible on /menu:", vis, "show_subscribe:", cfg.get("show_subscribe"))

    sub_cfg = normalize_promo_banner({**cfg, "enabled": True, "show_subscribe": True})
    for placement in ("above_header", "below_header", "above_footer"):
        html = app.jinja_env.get_template("partials/deals_promo_banner_slot.html").render(
            promo_banner={**sub_cfg, "placement": placement},
            placement=placement,
            promo_banner_image_key="promo_banner_image",
            inline_edit=False,
            csrf_token="test",
            current_store=s,
            pc=lambda k, d="": d,
            pb_page_style=lambda *a: "",
            vasset=lambda u: u,
        )
        assert "ok-deals-promo" in html
        assert "ok-deals-promo-sub" in html
    app.jinja_env.get_template("partials/deals_promo_banner_slot.html").render(
        promo_banner={**sub_cfg, "placement": "above_header"},
        placement="above_header",
        promo_banner_image_key="promo_banner_image",
        inline_edit=True,
        csrf_token="test",
        current_store=s,
        pc=lambda k, d="": d,
        pb_page_style=lambda *a: "",
        vasset=lambda u: u,
    )
    print("jinja subscribe banner (+ edit mode): OK")

if fail:
    print("FAILED", fail)
    sys.exit(1)
print("SMOKE_OK")
