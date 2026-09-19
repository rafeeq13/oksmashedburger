"""Retry pscp for paths that failed (network aborts). Usage: python tools/deploy_retry_failed.py"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PSCP = r"C:\Program Files\PuTTY\pscp.exe"
PLINK = r"C:\Program Files\PuTTY\plink.exe"
HOST = "root@2.24.192.10"
PORT = "3003"
PW = "FxSgigB@2JEL9w"
REMOTE = "/var/www/oksmashedburger"

RETRY = [
    "app/services/promo_page_targets.py",
    "app/services/subscribers.py",
    "app/services/staff_permissions.py",
    "app/templates/layouts/base.html",
    "app/templates/partials/inline_editor.html",
    "app/templates/partials/deals_promo_banner.html",
    "app/templates/partials/deals_promo_visit_popup.html",
    "app/static/js/app.js",
    "app/templates/admin/_mobile_header_deals_section.html",
    "app/templates/admin/coupons.html",
    "app/templates/admin/subscribers.html",
]


def upload(rel: str, attempts: int = 5) -> bool:
    local = ROOT / rel.replace("/", "\\")
    if not local.is_file():
        print("MISSING", rel)
        return False
    remote = f"{REMOTE}/{rel}"
    for i in range(attempts):
        r = subprocess.run(
            [PSCP, "-P", PORT, "-pw", PW, str(local), f"{HOST}:{remote}"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            print("OK", rel)
            return True
        print("RETRY", i + 1, rel, (r.stderr or r.stdout or "")[:100])
        time.sleep(2)
    return False


def main():
    failed = [rel for rel in RETRY if not upload(rel)]
    subprocess.run(
        f'echo y | "{PLINK}" -ssh {HOST} -P {PORT} -pw {PW} -batch '
        f'"systemctl restart oksmashedburger.service && sleep 2 && systemctl is-active oksmashedburger.service"',
        shell=True,
        check=True,
    )
    print("Restarted oksmashedburger.service")
    if failed:
        print("Still failed:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
