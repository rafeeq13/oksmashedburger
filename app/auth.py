"""Session-based web auth + Role-Based Access Control (SRS §4.1).

The signed, HTTP-only Flask session cookie holds the user id. JWT (already
installed) is reserved for the versioned REST API (SRS §5.4)."""
from functools import wraps
from flask import session, g, redirect, request, abort

from .extensions import db
from .models.user import User


def login_user(user):
    session["user_id"] = user.id
    session.permanent = True


def logout_user():
    session.pop("user_id", None)
    g.pop("_current_user", None)


def current_user():
    if "_current_user" not in g:
        uid = session.get("user_id")
        g._current_user = db.session.get(User, uid) if uid else None
    return g._current_user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect("/login?next=" + request.path)
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Restrict a view to the given role names (e.g. 'super_admin', 'store_manager')."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect("/login?next=" + request.path)
            if user.role.name not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
