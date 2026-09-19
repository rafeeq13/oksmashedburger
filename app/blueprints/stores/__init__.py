"""Store locator + choosing which location you're ordering from."""
from flask import Blueprint, render_template, session, redirect, request, abort, flash, jsonify

from app import cart as cartlib
from app.helpers import active_stores, find_store_for_zip, get_current_store, normalize_order_type, store_accepts_order_type
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
    unavailable = cartlib.unavailable_at_store(store)
    if unavailable:
        flash(
            f"Some items in your cart aren't available at {store.name}: "
            f"{', '.join(unavailable)}. Please choose items from this location's menu.",
            "error",
        )
    # go back where the user came from, or to the menu
    return redirect(request.args.get("next") or "/menu")


@bp.get("/api/deals-promo-popup")
def api_deals_promo_popup():
    """Visit-popup HTML after location is saved (used by app.js on the home page)."""
    from app.services.promo_banners import deals_visit_popup_partial_context

    ctx = deals_visit_popup_partial_context()
    if not ctx:
        return "", 204
    return render_template("partials/deals_promo_visit_popup.html", **ctx)


@bp.get("/api/select-store/<slug>")
def api_select_store(slug):
    """Set the current store WITHOUT redirecting (used by the locations page so
    selecting a location updates in place instead of reloading)."""
    store = Store.query.filter_by(slug=slug, is_active=True).first()
    if not store:
        return {"ok": False}, 404
    session["store_slug"] = slug
    session["context_set"] = True
    unavailable = cartlib.unavailable_at_store(store)
    return {"ok": True, "slug": store.slug, "name": store.name,
            "city": store.city, "zip": store.zip_code,
            "address": store.full_address,
            "phone": store.phone or "",
            "email": store.email or "",
            "map_query": store.map_query,
            "map_embed_src": store.map_embed_src,
            "hours_today": store.today_hours_with_day,
            "today_hours": store.today_hours,
            "open_now": store.open_now,
            "can_order": store.can_order,
            "scheduling_open": store.scheduling_open,
            "avg_prep_minutes": store.avg_prep_minutes,
            "accepts_delivery": store.accepts_delivery,
            "accepts_pickup": store.accepts_pickup,
            "cart_unavailable": unavailable}


@bp.get("/api/schedule")
def api_schedule():
    """Save a scheduled (future) order time without a reload | used when the store
    is closed for ASAP and the customer must pick a time before ordering."""
    val = (request.args.get("schedule_at") or "").strip()
    if not val:
        # an empty value means "cancel the schedule, order as soon as possible";
        # it used to 400, so there was no way back to an ASAP order
        session.pop("schedule_at", None)
        session["context_set"] = True
        return {"ok": True, "schedule_at": ""}
    # The selects only offer valid slots, but a request can be made by hand, and
    # an out-of-hours time would sail through to checkout and fail there.
    store = get_current_store()
    if store and not store.accepts_schedule_at(val):
        return {"ok": False, "error": "That time is outside the store's opening hours."}, 400

    session["schedule_at"] = val
    session["context_set"] = True
    return {"ok": True, "schedule_at": val}


@bp.get("/api/order-type/<otype>")
def api_order_type(otype):
    """Switch delivery / pickup without a reload."""
    if otype not in ORDER_TYPES:
        return {"ok": False}, 400
    store = get_current_store()
    if not store_accepts_order_type(store, otype):
        return {"ok": False, "error": "That order type isn't available at this location."}, 400
    session["order_type"] = otype
    session["context_set"] = True
    return {"ok": True, "order_type": otype}


@bp.get("/api/delivery-quote")
def api_delivery_quote():
    """Return zone-based delivery fee and availability for the current store."""
    store = get_current_store()
    if not store:
        return jsonify(ok=False, error="No store selected"), 400

    zip_code = (request.args.get("zip") or "").strip()
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    tip = request.args.get("tip", type=float) or 0.0
    from app.address import format_address
    address_label = (request.args.get("address") or "").strip()
    line1 = (request.args.get("line1") or "").strip()
    line2 = (request.args.get("line2") or "").strip()
    city = (request.args.get("city") or "").strip()
    state = (request.args.get("state") or "").strip()
    search = (request.args.get("search") or "").strip()
    if not address_label:
        address_label = format_address(line1, line2, city, state, zip_code) or search

    s = cartlib.summary(
        store, tip=tip, order_type="delivery",
        address_zip=zip_code, address_lat=lat, address_lng=lng,
        address_label=address_label, address_line1=line1, address_line2=line2,
        address_city=city, address_state=state, address_search=search,
    )
    zone = s.get("delivery_zone") or {}
    return jsonify(
        ok=True,
        in_zone=bool(zone.get("in_zone")),
        zone_name=zone.get("zone_name"),
        delivery_fee=s["delivery_fee"],
        base_delivery=s["base_delivery"],
        delivery_free=bool(s["promo"].get("delivery_discount")),
        min_order=zone.get("min_order"),
        est_minutes=zone.get("est_minutes"),
        distance_miles=zone.get("distance_miles"),
        message=zone.get("message") or "",
        address_label=zone.get("address_label") or address_label,
        subtotal=s["subtotal"],
        tax=s["tax"],
        total=s["total"],
        total_before_tip=round(s["total"] - s["tip"], 2),
    )


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
        unavailable = cartlib.unavailable_at_store(store)
        if unavailable:
            flash(
                f"Some items in your cart aren't available at {store.name}: "
                f"{', '.join(unavailable)}. Please choose items from this location's menu.",
                "error",
            )
    session["context_set"] = True  # user has chosen store/type → stop auto-opening the modal

    ot = request.form.get("order_type", "delivery")
    if ot in ORDER_TYPES and store_accepts_order_type(store or get_current_store(), ot):
        session["order_type"] = ot
    else:
        session["order_type"] = normalize_order_type(store)

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
