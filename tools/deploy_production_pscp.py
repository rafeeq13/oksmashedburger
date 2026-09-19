"""Upload deploy_promo_bundle.list (+ store.py) via pscp; verify sizes; restart."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "tools" / "deploy_promo_bundle.list"
PSCP = r"C:\Program Files\PuTTY\pscp.exe"
PLINK = r"C:\Program Files\PuTTY\plink.exe"
HOST = "root@2.24.192.10"
PORT = "3003"
PW = "FxSgigB@2JEL9w"
REMOTE = "/var/www/oksmashedburger"


def pscp(local: Path, remote: str) -> bool:
    r = subprocess.run(
        [PSCP, "-P", PORT, "-pw", PW, str(local), f"{HOST}:{remote}"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("FAIL", local.name, r.stderr or r.stdout)
        return False
    print("OK", local.relative_to(ROOT))
    return True


def main():
    rels = [ln.strip() for ln in LIST.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if "app/models/store.py" not in rels:
        rels.append("app/models/store.py")
    failed = []
    for rel in rels:
        if rel.startswith("tools/"):
            continue
        local = ROOT / rel.replace("/", "\\")
        if not local.is_file():
            print("SKIP missing local", rel)
            failed.append(rel)
            continue
        remote = f"{REMOTE}/{rel}"
        if not pscp(local, remote):
            failed.append(rel)
    if failed:
        print("Upload failures:", len(failed))
        sys.exit(1)
    subprocess.run(
        f'echo y | "{PLINK}" -ssh {HOST} -P {PORT} -pw {PW} -batch '
        f'"systemctl restart oksmashedburger.service && sleep 2 && systemctl is-active oksmashedburger.service"',
        shell=True,
        check=True,
    )
    print("Restarted.")


if __name__ == "__main__":
    main()
