"""Upload files from deploy_promo_bundle.list to production (same flow as plink_upload)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("deploy_promo_bundle.list")
REMOTE_ROOT = "/var/www/oksmashedburger"
UPLOAD = ROOT / "tools" / "plink_upload.py"


def main():
    paths = [
        line.strip()
        for line in LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    failed = []
    for rel in paths:
        local = ROOT / rel.replace("/", "\\") if "\\" in rel else ROOT / rel
        if not local.is_file():
            print("SKIP missing:", rel)
            failed.append(rel)
            continue
        remote = f"{REMOTE_ROOT}/{rel.replace(chr(92), '/')}"
        print("==>", rel)
        r = subprocess.run(
            [sys.executable, str(UPLOAD), str(local), remote],
            cwd=str(ROOT),
        )
        if r.returncode != 0:
            failed.append(rel)
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    sys.path.insert(0, str(ROOT / "tools"))
    import plink_upload

    plink_upload.plink(
        "systemctl restart oksmashedburger.service && systemctl is-active oksmashedburger.service"
    )
    print("Deploy done.")


if __name__ == "__main__":
    main()
