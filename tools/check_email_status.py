"""One-off: print per-store SMTP status and recent notification log."""
from app import create_app
from app.models.store import Store
from app.models.notification import Notification
from app.integrations import smtp_gateway
from app.integrations.config import integration_env, active_integration_config, integration_enabled

app = create_app()
with app.app_context():
    print("=== STORES SMTP ===")
    for s in Store.query.filter_by(is_active=True).order_by(Store.name).all():
        env = integration_env(s)
        integ = s.integration("smtp")
        en = integration_enabled(s, "smtp")
        ok = smtp_gateway.is_enabled(s)
        cfg = active_integration_config(s, "smtp") if integ else {}
        host = (cfg.get("smtp_host") or "")[:40]
        frm = cfg.get("from_email") or ""
        print(f"{s.slug:25} env={env:10} enabled={en!s:5} ready={ok!s:5} host={host!r} from={frm!r}")
    print("=== RECENT NOTIFICATIONS (email) ===")
    q = Notification.query.filter_by(channel="email").order_by(Notification.created_at.desc()).limit(20)
    for n in q.all():
        recip = (n.recipient or "")[:50]
        print(f"{n.created_at} {n.event:20} {n.status:10} {recip}")
