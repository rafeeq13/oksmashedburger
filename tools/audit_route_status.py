"""Hit common routes and report non-2xx/3xx status codes (500 audit helper)."""
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"

PUBLIC = [
    "/", "/menu", "/menu?q=shake", "/about", "/catering", "/careers", "/news", "/faq",
    "/rewards", "/gift-cards", "/deals", "/locations", "/contact", "/login", "/register",
    "/forgot-password", "/cart", "/checkout", "/healthz", "/item/combo-1", "/api/deals",
    "/api/schedule", "/webhooks/health",
]

ADMIN = [
    "/admin", "/admin/orders", "/admin/customers", "/admin/menu", "/admin/coupons",
    "/admin/gift-cards", "/admin/drivers", "/admin/staff", "/admin/locations",
    "/admin/settings", "/admin/canvas", "/admin/builder", "/admin/page-content",
    "/admin/content", "/admin/site-images", "/admin/email-templates", "/admin/design",
    "/admin/theme", "/admin/features", "/admin/reviews", "/admin/integrations",
    "/admin/notifications", "/admin/messages", "/admin/subscribers",
]

EXPECTED_4XX = {"/checkout", "/cart", "/admin"}


def check(path):
    try:
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "audit-route-status/1"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as exc:
        return "ERR", str(exc)[:80]


def main():
    fails = []
    for path in PUBLIC + ADMIN:
        code, err = check(path)
        if code == "ERR":
            fails.append((path, code, err))
        elif isinstance(code, int) and code >= 500:
            fails.append((path, code, "server error"))
        elif isinstance(code, int) and code >= 400 and path not in EXPECTED_4XX:
            fails.append((path, code, "unexpected client error"))
    print("base:", BASE)
    print("checked:", len(PUBLIC) + len(ADMIN))
    print("failures:", len(fails))
    for row in fails:
        print(f"{row[0]}\t{row[1]}\t{row[2]}")


if __name__ == "__main__":
    main()
