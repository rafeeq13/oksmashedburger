"""Customer order tracking (SRS FR-6.3) + a JSON status endpoint for polling."""
from datetime import timedelta
from urllib.parse import quote

from flask import Blueprint, render_template, jsonify, request, flash

from app.extensions import db
from app.models.order import Order
from app.services.orders import TRACK_STAGES, STAGE_META, stage_index

bp = Blueprint("tracking", __name__)


def _delivery_address(order):
    if order.address:
        return order.address
    parts = [order.address_line1, order.address_line2,
             order.address_city, order.address_state, order.address_zip]
    return ", ".join(p for p in parts if p)


def _tracking_map_src(order):
    store = order.store
    if order.order_type == "delivery":
        dest = _delivery_address(order)
        if dest and store:
            return (
                "https://maps.google.com/maps?saddr="
                + quote(store.full_address)
                + "&daddr="
                + quote(dest)
                + "&output=embed"
            )
        if dest:
            return f"https://maps.google.com/maps?q={quote(dest)}&z=15&output=embed"
    if store:
        return store.map_embed_src
    return "https://maps.google.com/maps?q=Philadelphia&z=12&output=embed"


def _context(order):
    """Everything the tracker UI needs — shared by the page render and the JSON
    poll endpoint so live updates stay in sync with the server."""
    idx = stage_index(order.status)
    stages = []
    for i, s in enumerate(TRACK_STAGES):
        if s == "out_for_delivery" and order.order_type != "delivery":
            continue
        state = "done" if i < idx else ("active" if i == idx else "todo")
        stages.append({"key": s, "label": STAGE_META[s]["label"], "icon": STAGE_META[s]["icon"], "state": state})

    meta = STAGE_META.get(order.status, {})
    prep = order.store.avg_prep_minutes if order.store else 15
    eta_minutes = prep + (25 if order.order_type == "delivery" else 0)
    eta_dt = order.scheduled_for or (order.created_at + timedelta(minutes=eta_minutes))
    eta_time = eta_dt.strftime("%I:%M %p").lstrip("0")

    handler = None
    if order.status == "out_for_delivery" and order.delivery and order.delivery.driver:
        handler = {"icon": "user", "text": order.delivery.driver.name + " is on the way"}
    elif order.status in ("placed", "confirmed", "preparing", "ready"):
        handler = {"icon": "kitchen-set",
                   "text": (order.store.name + " kitchen team" if order.store else "Our kitchen team")}

    return {
        "number": order.number, "status": order.status, "stages": stages,
        "headline": meta.get("headline", ""), "desc": meta.get("desc", ""),
        "eta_time": eta_time, "eta_minutes": eta_minutes, "handler": handler,
        "ready_verb": "Arriving by" if order.order_type == "delivery" else "Ready by",
        "scheduled": bool(order.scheduled_for),
        # A full-reload is used for these because the whole page layout changes
        # (driver/map card appears, or a terminal state card replaces the tracker).
        "reload": order.status in ("out_for_delivery", "completed", "cancelled"),
    }


def _render(order):
    return render_template(
        "orders/tracking.html",
        order=order,
        map_embed_src=_tracking_map_src(order),
        **_context(order),
    )


def _lookup_order():
    number = (request.args.get("order") or "").strip().upper()
    email = (request.args.get("email") or "").strip().lower()
    if number:
        return Order.query.filter_by(number=number).first(), "number"
    if email:
        return (
            Order.query.filter(db.func.lower(Order.customer_email) == email)
            .order_by(Order.created_at.desc())
            .first(),
            "email",
        )
    return None, None


@bp.get("/tracking")
def tracking():
    order, via = _lookup_order()
    if via == "number" and not order:
        flash("We couldn't find that order number. Please check and try again.", "error")
    elif via == "email" and not order:
        flash("We couldn't find an order for that email.", "error")
    elif via == "email" and order:
        n = Order.query.filter(db.func.lower(Order.customer_email) == request.args.get("email", "").strip().lower()).count()
        if n > 1:
            flash("Showing your most recent order. Use the order number for a specific one.", "info")
    if order:
        return _render(order)
    return render_template("orders/tracking.html", order=None, stages=[], headline="")


@bp.get("/tracking/<number>")
def tracking_number(number):
    order = Order.query.filter_by(number=number).first_or_404()
    return _render(order)


@bp.get("/api/orders/<number>/status")
def status_json(number):
    order = Order.query.filter_by(number=number).first()
    if not order:
        return jsonify({"error": "not found"}), 404
    return jsonify(_context(order))
