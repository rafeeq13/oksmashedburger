"""Replace old public domain in stored integration/webhook settings."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OLD = "fooddeliveryaudit.com"
NEW = "oksmashedburger.com"


def main():
    from app import create_app
    from app.extensions import db
    from app.models.store import StoreIntegration
    from app.models.site import SiteSetting

    app = create_app()
    with app.app_context():
        changed = 0
        for row in StoreIntegration.query.all():
            cfg = dict(row.config or {})
            touched = False
            for key, val in list(cfg.items()):
                if isinstance(val, str) and OLD in val:
                    cfg[key] = val.replace(OLD, NEW)
                    touched = True
            if touched:
                row.config = cfg
                changed += 1
                print("integration", row.provider, "store", row.store_id, "updated")
        for row in SiteSetting.query.all():
            val = row.value or ""
            if OLD in val:
                row.value = val.replace(OLD, NEW)
                changed += 1
                print("setting", row.key, "updated")
        db.session.commit()
        print("done, rows_changed=", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
