"""Authentication: login, register (customer), logout, password reset."""
from flask import Blueprint, render_template, request, redirect, flash, current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db, limiter
from app.models.user import User, Role
from app.auth import login_user, logout_user, current_user

bp = Blueprint("auth", __name__)

RESET_MAX_AGE = 3600          # one hour
_RESET_SALT = "ok-password-reset"


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_RESET_SALT)


def _reset_token(user):
    """Signed, expiring, single-use. Single-use comes from binding the token to
    the CURRENT password hash: once the password changes the fingerprint no
    longer matches, so an old link (or a re-used one) stops working. No table,
    no cleanup job."""
    fingerprint = (user.password_hash or "")[-12:]
    return _serializer().dumps({"uid": user.id, "fp": fingerprint})


def _user_from_token(token):
    try:
        data = _serializer().loads(token, max_age=RESET_MAX_AGE)
    except SignatureExpired:
        return None, "That reset link has expired. Please request a new one."
    except BadSignature:
        return None, "That reset link is not valid. Please request a new one."
    user = db.session.get(User, data.get("uid"))
    if not user or not user.is_active:
        return None, "That reset link is not valid. Please request a new one."
    if (user.password_hash or "")[-12:] != data.get("fp"):
        return None, "That reset link has already been used. Please request a new one."
    return user, None


def _mail(fn, *args):
    """Mail must never break the auth flow it is attached to."""
    try:
        from app.services import mailer
        getattr(mailer, fn)(*args)
    except Exception as e:
        current_app.logger.warning("auth mail (%s) failed: %s", fn, e)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 40 per hour", methods=["POST"])
def login():
    if current_user():
        return redirect("/account")
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.password_hash and user.is_active and user.check_password(password):
            login_user(user)
            return redirect(request.args.get("next") or "/account")
        flash("Incorrect email or password.", "error")
    return render_template("pages/login.html")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def register():
    if current_user():
        return redirect("/account")
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        agree = request.form.get("agree")

        first, _, last = name.partition(" ")
        if not email or "@" not in email:
            flash("Please enter a valid email address.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif not agree:
            flash("Please accept the Terms & Privacy Policy.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            role = Role.query.filter_by(name="customer").first()
            user = User(email=email, first_name=first, last_name=last, phone=phone,
                        role=role, loyalty_points=100)  # 100 welcome points
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            _mail("welcome", user)
            login_user(user)
            flash("Welcome to OK Rewards — 100 bonus points added!", "success")
            return redirect("/account")
    return render_template("pages/register.html")


@bp.get("/logout")
def logout():
    logout_user()
    return redirect("/")


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("4 per minute; 15 per hour", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.is_active and user.password_hash:
            link = url_for("auth.reset_password", token=_reset_token(user), _external=True)
            _mail("password_reset", user, link)
        # Same answer either way — never reveal whether an address is registered.
        flash("If an account exists for that email, a reset link is on its way.", "success")
    return render_template("pages/forgot-password.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute; 30 per hour", methods=["POST"])
def reset_password(token):
    user, error = _user_from_token(token)
    if error:
        flash(error, "error")
        return redirect("/forgot-password")

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user.set_password(password)
            db.session.commit()          # this also invalidates the token
            _mail("password_changed", user)
            login_user(user)
            flash("Your password has been reset. You're signed in.", "success")
            return redirect("/account")

    return render_template("pages/reset-password.html", token=token, email=user.email)
