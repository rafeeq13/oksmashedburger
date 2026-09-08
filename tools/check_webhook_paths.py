import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.models.store import Store
from app.integrations.webhook_urls import webhook_path, resolve_webhook_url, webhook_settings

app = create_app()
with app.app_context():
    s = Store.query.filter_by(slug="west-philadelphia").first()
    print("path:", webhook_path("uber_direct", "3517"))
    print("resolve:", resolve_webhook_url(s, "uber_direct", "https://oksmashedburger.com"))
    print("wh settings:", webhook_settings(s))
