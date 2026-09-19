from app import create_app
from app.models.store import Store
from app.integrations import smtp_gateway

app = create_app()
with app.app_context():
    for s in Store.query.filter_by(is_active=True):
        print(s.slug, "smtp", smtp_gateway.is_enabled(s))
