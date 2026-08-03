"""CSRF protection for state-changing form posts (SRS NFR-2.3)."""
import secrets
from flask import session, request, abort

_SAFE = {"GET", "HEAD", "OPTIONS"}
# REST API uses JWT; /form-submit receives posts from admin-built (GrapesJS) pages
# whose arbitrary HTML forms can't carry the session CSRF token; /unsubscribe is
# posted to by Gmail and Outlook themselves (RFC 8058 one-click), which have no
# session at all — that route is safe without CSRF because its own signed token
# is the authorisation, and the only thing it can do is opt an address out.
_EXEMPT_PREFIXES = ("/api/", "/form-submit", "/unsubscribe/")


def get_csrf_token():
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok


def init_csrf(app):
    @app.before_request
    def _csrf_protect():
        if request.method in _SAFE:
            return
        if request.path.startswith(_EXEMPT_PREFIXES):
            return
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not sent or sent != session.get("_csrf"):
            abort(400, description="Invalid or missing CSRF token.")
