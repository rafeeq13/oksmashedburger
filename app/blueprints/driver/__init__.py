"""Driver app view — assigned deliveries, status updates, proof of delivery (SRS FR-8.4)."""
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, abort

from app.extensions import db
from app.auth import current_user, roles_required
from app.models.delivery import Driver, Delivery

bp = Blueprint("driver", __name__)
DRIVER_ROLES = ("driver", "super_admin", "store_manager")


@bp.get("/driver")
@roles_required(*DRIVER_ROLES)
def dashboard():
    driver = Driver.query.filter_by(user_id=current_user().id).first()
    active, done = [], []
    if driver:
        active = Delivery.query.filter(Delivery.driver_id == driver.id,
                                       Delivery.status.in_(["assigned", "picked_up"])).all()
        done = (Delivery.query.filter(Delivery.driver_id == driver.id, Delivery.status == "delivered")
                .order_by(Delivery.delivered_at.desc()).limit(5).all())
    return render_template("driver/dashboard.html", driver=driver, active=active, done=done)


@bp.post("/driver/deliveries/<int:did>/status")
@roles_required(*DRIVER_ROLES)
def update(did):
    d = Delivery.query.get_or_404(did)
    user = current_user()
    if user.role.name == "driver" and (not d.driver or d.driver.user_id != user.id):
        abort(403)

    now = datetime.now(timezone.utc)
    action = request.form.get("action")
    if action == "pickup" and d.status == "assigned":
        d.status = "picked_up"
        d.picked_up_at = now
    elif action == "deliver" and d.status in ("assigned", "picked_up"):
        d.status = "delivered"
        d.delivered_at = now
        d.proof = request.form.get("proof", "").strip() or "Left at door"
        d.order.status = "completed"  # delivery done -> order completed
    db.session.commit()
    return redirect("/driver")
