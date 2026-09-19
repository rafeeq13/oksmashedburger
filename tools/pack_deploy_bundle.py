"""Create deploy_bundle.tar.gz from deploy_promo_bundle.list (+ store.py)."""
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "tools" / "deploy_promo_bundle.list"
OUT = ROOT / "tools" / "deploy_bundle.tar.gz"

rels = [ln.strip() for ln in LIST.read_text(encoding="utf-8").splitlines() if ln.strip()]
if "app/models/store.py" not in rels:
    rels.append("app/models/store.py")

with tarfile.open(OUT, "w:gz") as tar:
    for rel in rels:
        if rel.startswith("tools/"):
            continue
        local = ROOT / rel
        if local.is_file():
            tar.add(local, arcname=rel)
        else:
            print("skip missing", rel)
print("wrote", OUT, OUT.stat().st_size, "bytes")
