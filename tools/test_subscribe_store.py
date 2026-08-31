import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.contact import Subscriber


def csrf(c, path="/"):
    html = c.get(path).data.decode("utf-8", "replace")
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else ""


def main():
    app = create_app()
    with app.app_context():
        c = app.test_client()
        email = "pytest-sub-loc@example.invalid"
        Subscriber.query.filter_by(email=email).delete()
        db.session.commit()
        with c.session_transaction() as sess:
            sess["store_slug"] = "south-snyder"
        r = c.post("/subscribe", data={
            "email": email,
            "store_slug": "south-snyder",
            "_csrf": csrf(c, "/"),
        }, follow_redirects=True)
        sub = Subscriber.query.filter_by(email=email).first()
        print("status", r.status_code)
        if not sub:
            print("FAIL: no subscriber row")
            return 1
        print("store", sub.store.name if sub.store else None, "store_id", sub.store_id)
        Subscriber.query.filter_by(email=email).delete()
        db.session.commit()
        return 0 if sub.store and sub.store.slug == "south-snyder" else 2


if __name__ == "__main__":
    raise SystemExit(main())
