"""Store locator + choosing which location you're ordering from."""
from flask import Blueprint, render_template, session, redirect, request, abort, flash

from app.helpers import active_stores, find_store_for_zip
from app.models.store import Store

bp = Blueprint("stores", __name__)

ORDER_TYPES = ("delivery", "pickup")


@bp.get("/locations")
def locations():
    return render_template("stores/locations.html", stores=active_stores())


@bp.get("/set-location/<slug>")
def set_location(slug):
    store = Store.query.filter_by(slug=slug, is_active=True).first()
    if not store:
        abort(404)
    session["store_slug"] = slug
    # go back where the user came from, or to the menu
    return redirect(request.args.get("next") or "/menu")


@bp.get("/api/select-store/<slug>")
def api_select_store(slug):
    """Set the current store WITHOUT redirecting (used by the locations page so
    selecting a location updates in place instead of reloading)."""
    store = Store.query.filter_by(slug=slug, is_active=True).first()
    if not store:
        return {"ok": False}, 404
    session["store_slug"] = slug
    session["context_set"] = True
    return {"ok": True, "slug": store.slug, "name": store.name,
            "city": store.city, "zip": store.zip_code}


@bp.get("/api/schedule")
def api_schedule():
    """Save a scheduled (future) order time without a reload — used when the store
    is closed for ASAP and the customer must pick a time before ordering."""
    val = (request.args.get("schedule_at") or "").strip()
    if not val:
        return {"ok": False}, 400
    session["schedule_at"] = val
    session["context_set"] = True
    return {"ok": True, "schedule_at": val}


@bp.get("/api/order-type/<otype>")
def api_order_type(otype):
    """Switch delivery / pickup without a reload."""
    if otype not in ORDER_TYPES:
        return {"ok": False}, 400
    session["order_type"] = otype
    session["context_set"] = True
    return {"ok": True, "order_type": otype}


@bp.post("/order-context")
def order_context():
    """Set the ordering session: which store (by slug or nearest ZIP), order
    type (delivery/pickup) and ASAP-vs-scheduled."""
    slug = (request.form.get("store") or "").strip()
    zip_code = (request.form.get("zip") or "").strip()
    store = None
    if slug:
        store = Store.query.filter_by(slug=slug, is_active=True).first()
    elif zip_code:
        store = find_store_for_zip(zip_code)
    if store:
        session["store_slug"] = store.slug
    session["context_set"] = True  # user has chosen store/type → stop auto-opening the modal

    ot = request.form.get("order_type", "delivery")
    if ot in ORDER_TYPES:
        session["order_type"] = ot

    if request.form.get("schedule") == "later" and request.form.get("schedule_at"):
        session["schedule_at"] = request.form.get("schedule_at")
    else:
        session.pop("schedule_at", None)

    active = session.get("store_slug")
    s = Store.query.filter_by(slug=active).first() if active else None
    if s:
        when = "scheduled" if session.get("schedule_at") else "now"
        flash(f"Ordering {session.get('order_type', 'delivery')} from {s.name} ({when}).", "success")
    return redirect(request.form.get("next") or "/menu")
