"""Checkout → order creation → per-store payment → confirmation."""
from decimal import Decimal
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, session, flash, jsonify, current_app

from app.extensions import db
from app import cart as cartlib
from app.helpers import fulfillment_available, get_current_store, get_order_type, store_accepts_order_type
from app.auth import current_user
from app.models.order import Order, OrderItem, Payment
from app.models.promo import Coupon, GiftCard
from app.integrations.stripe_gateway import (
    charge, store_stripe_config, is_connected, stripe_checkout_mode,
    create_payment_intent, verify_payment_intent, update_payment_intent,
)
from app.integrations.google_maps import store_google_maps_key
from app.integrations.config import integration_env, should_simulate
from app.address import address_from_form

bp = Blueprint("checkout", __name__)


def _merge_session_schedule(store, form):
    """Pre-fill checkout from menu schedule (session schedule_at)."""
    form = dict(form or {})
    if not store:
        return form
    session_val = (session.get("schedule_at") or "").strip()
    sched = (form.get("scheduled_for") or "").strip() or session_val
    if sched and store.accepts_schedule_at(sched):
        form["scheduled_for"] = sched
        # Menu schedule wins over a stale draft that still had ASAP selected.
        form["fulfillment"] = "scheduled"
    return form


def _checkout_draft():
    """Remember what the customer entered when validation bounces them back."""
    tip = request.form.get("tip", "0")
    store = get_current_store()
    subtotal = cartlib.summary(store).get("subtotal", 0) if store else 0
    presets = (store.tip_presets if store and store.tip_presets else [15, 18, 20])
    preset_vals = {f"{round(subtotal * p / 100, 2):.2f}" for p in presets}
    try:
        tip_f = float(tip or 0)
    except (TypeError, ValueError):
        tip_f = 0.0
    tip = f"{tip_f:.2f}"
    tip_custom = tip_f > 0 and tip not in preset_vals
    addr = address_from_form(request.form)
    return {
        "order_type": request.form.get("order_type", "delivery"),
        "fulfillment": request.form.get("fulfillment", "asap"),
        "scheduled_for": request.form.get("scheduled_for", ""),
        "address_line1": addr["line1"],
        "address_line2": addr["line2"],
        "address_city": addr["city"],
        "address_state": addr["state"],
        "address_zip": addr["zip"],
        "address_lat": request.form.get("address_lat", ""),
        "address_lng": request.form.get("address_lng", ""),
        "address_search": request.form.get("address_search", "").strip(),
        "name": request.form.get("name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "email": request.form.get("email", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "tip": tip,
        "tip_custom": tip_custom,
        "payment_method": request.form.get("payment_method", "card"),
        "card_number": request.form.get("card_number", ""),
        "card_exp": request.form.get("card_exp", ""),
        "card_cvc": request.form.get("card_cvc", ""),
        "card_name": request.form.get("card_name", ""),
    }


def _checkout_error(message):
    session["checkout_draft"] = _checkout_draft()
    flash(message, "error")
    return redirect("/checkout")


def _checkout_email(raw=None):
    """Normalized email from checkout form; empty if missing/invalid."""
    from app.services.email_delivery import is_valid_email

    email = (raw if raw is not None else request.form.get("email", "")).strip().lower()
    if not is_valid_email(email):
        return ""
    return email


def _render_checkout(store, form=None):
    form = _merge_session_schedule(store, form or {})
    ot = form.get("order_type") or get_order_type()
    if ot:
        session["order_type"] = ot
    try:
        tip = float(form.get("tip") or 0)
    except (TypeError, ValueError):
        tip = 0.0
    addr_zip = (form.get("address_zip") or "").strip()
    addr_lat = form.get("address_lat")
    addr_lng = form.get("address_lng")
    try:
        addr_lat_f = float(addr_lat) if addr_lat else None
    except (TypeError, ValueError):
        addr_lat_f = None
    try:
        addr_lng_f = float(addr_lng) if addr_lng else None
    except (TypeError, ValueError):
        addr_lng_f = None
    addr_kw = {"address_zip": addr_zip, "address_lat": addr_lat_f, "address_lng": addr_lng_f}
    calc_ot = ot or "pickup"
    s = cartlib.summary(store, tip=tip, order_type=calc_ot, **addr_kw)
    s_delivery = s if calc_ot == "delivery" else cartlib.summary(store, tip=tip, order_type="delivery", **addr_kw)
    s_pickup = s if calc_ot == "pickup" else cartlib.summary(store, tip=tip, order_type="pickup", **addr_kw)
    u = current_user()
    default_address = None
    if u:
        from app.models.address import UserAddress
        default_address = (UserAddress.query.filter_by(user_id=u.id, is_default=True).first()
                           or UserAddress.query.filter_by(user_id=u.id).first())
    sched_days = store.schedule_days(store.local_now()) if store else []
    return render_template(
        "checkout/checkout.html", store=store, summary=s, user=u, form=form,
        default_address=default_address,
        sched_days=sched_days,
        stripe_pub_key=store_stripe_config(store).get("publishable_key", ""),
        stripe_connected=is_connected(store),
        stripe_checkout_mode=stripe_checkout_mode(store) if store else "off",
        integration_env=integration_env(store) if store else "sandbox",
        checkout_delivery_fee=s_delivery["delivery_fee"],
        checkout_delivery_free=bool(s_delivery["promo"].get("delivery_discount")),
        checkout_total_delivery=s_delivery["total"],
        checkout_total_pickup=s_pickup["total"],
        google_maps_api_key=store_google_maps_key(store),
    )


@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    store = get_current_store()
    if not cartlib.get_cart():
        return redirect("/menu")
    if not fulfillment_available(store):
        flash("Delivery and pickup are unavailable at this location right now.", "error")
        return redirect("/cart")

    if request.method == "POST":
        order_type = (request.form.get("order_type") or "").strip()
        if not order_type or not store_accepts_order_type(store, order_type):
            return _checkout_error("That order type isn't available at this location.")
        method = request.form.get("payment_method", "card")
        tip = request.form.get("tip", type=float) or 0.0

        # ── Open/closed + scheduling enforcement ─────────────────────
        fulfillment = request.form.get("fulfillment", "asap")
        scheduled_for = None
        if fulfillment == "scheduled":
            if not (store and store.scheduling_open):
                return _checkout_error("Scheduled ordering isn't available for this store right now.")
            sched_val = (request.form.get("scheduled_for") or "").strip()
            if not sched_val or not store.accepts_schedule_at(sched_val):
                return _checkout_error(
                    "Please choose a pickup time within our opening hours "
                    "(same slots as on the menu)."
                )
            try:
                scheduled_for = datetime.strptime(sched_val, "%Y-%m-%dT%H:%M")
            except (ValueError, TypeError):
                return _checkout_error("Please choose a valid date and time for your scheduled order.")
            session["schedule_at"] = sched_val
        else:  # ASAP
            if not (store and store.open_now):
                return _checkout_error(f"{store.name if store else 'This store'} is closed for immediate orders - "
                      "please schedule your order for later.")

        # A delivery order without an address is undeliverable, and the browser
        # `required` attribute is not a guarantee | it is trivially bypassed.
        addr = address_from_form(request.form)
        if order_type == "delivery" and not addr["line1"]:
            return _checkout_error("Please enter a delivery street address.")

        if order_type == "delivery":
            from app.services.delivery_zones import match_delivery_zone
            zone = match_delivery_zone(
                store, addr["zip"], addr["lat"], addr["lng"],
                line1=addr["line1"], line2=addr["line2"], city=addr["city"],
                state=addr["state"], search=request.form.get("address_search", "").strip(),
            )
            if not zone["in_zone"]:
                return _checkout_error(zone["message"] or "We can't deliver to that address.")

        s = cartlib.summary(
            store, tip=tip, order_type=order_type,
            address_zip=addr["zip"], address_lat=addr["lat"], address_lng=addr["lng"],
            address_line1=addr["line1"], address_line2=addr["line2"],
            address_city=addr["city"], address_state=addr["state"],
            address_search=request.form.get("address_search", "").strip(),
        )

        if order_type == "delivery":
            min_order = (s.get("delivery_zone") or {}).get("min_order")
            if min_order and s["subtotal"] < min_order:
                return _checkout_error(
                    "Minimum order for your delivery area is $%.2f (your subtotal is $%.2f)."
                    % (min_order, s["subtotal"])
                )

        customer_email = _checkout_email()
        if not customer_email:
            return _checkout_error(
                "Please enter a valid email address. We need it for your receipt, "
                "order updates, and kitchen tickets."
            )

        order = Order(
            store=store, user=current_user(), order_type=order_type,
            scheduled_for=scheduled_for,
            customer_name=request.form.get("name", "").strip(),
            customer_email=customer_email,
            customer_phone=request.form.get("phone", "").strip(),
            address=addr["one_line"],
            address_line1=addr["line1"],
            address_line2=addr["line2"] or None,
            address_city=addr["city"] or None,
            address_state=addr["state"] or None,
            address_zip=addr["zip"] or None,
            address_lat=addr["lat"],
            address_lng=addr["lng"],
            notes=request.form.get("notes", "").strip(),
            subtotal=Decimal(str(s["subtotal"])), tax=Decimal(str(s["tax"])),
            delivery_fee=Decimal(str(s["delivery_fee"])), tip=Decimal(str(s["tip"])),
            discount=Decimal(str(s["order_discount"])),
            coupon_code=(s["promo"]["code"] if (s["promo"]["discount"] or s["promo"]["delivery_discount"]) else None),
            points_redeemed=s["points"]["points_used"],
            gift_card_applied=Decimal(str(s["giftcard"]["applied"])),
            total=Decimal(str(s["total"])), payment_method=method,
        )
        db.session.add(order)
        db.session.flush()
        order.number = f"OK-{4000 + order.id}"

        for it in cartlib.get_cart():
            db.session.add(OrderItem(
                order=order, product_id=it["product_id"], name=it["name"],
                unit_price=Decimal(str(it["unit_price"])), qty=it["qty"],
                options=it["options"], line_total=Decimal(str(round(it["unit_price"] * it["qty"], 2))),
            ))

        # Apply promotions: coupon usage, points deduction, gift-card balance.
        if order.coupon_code:
            c = Coupon.query.filter_by(code=order.coupon_code).first()
            if c:
                c.used_count += 1
        if s["points"]["points_used"] and order.user:
            order.user.loyalty_points = max(0, order.user.loyalty_points - s["points"]["points_used"])
        if s["giftcard"]["applied"] > 0 and s["giftcard"]["code"]:
            gc = GiftCard.query.filter_by(code=s["giftcard"]["code"]).first()
            if gc:
                gc.balance = max(Decimal("0"), gc.balance - Decimal(str(s["giftcard"]["applied"])))

        # Payment | routed through THIS store's own Stripe account.
        payment_result = None
        if method == "card":
            from app.services.order_details import stripe_payment_update
            stripe_update = stripe_payment_update(order)
            stripe_mode = stripe_checkout_mode(store)
            intent_id = (request.form.get("stripe_payment_intent") or "").strip()
            if stripe_mode == "elements" and not should_simulate(store, "stripe") and not intent_id:
                db.session.rollback()
                return _checkout_error("Card payment was not completed. Please try again.")

            if intent_id:
                payment_result = verify_payment_intent(store, intent_id, s["total"])
                if payment_result["status"] == "succeeded":
                    meta_result = update_payment_intent(store, intent_id, **stripe_update)
                    if meta_result["status"] != "ok":
                        payment_result["raw"]["stripe_update"] = meta_result.get("raw") or {}
            else:
                payment_result = charge(store, s["total"], metadata=stripe_update.get("metadata"))

            if payment_result["status"] != "succeeded":
                db.session.rollback()
                err = (payment_result.get("raw") or {}).get("error") or "Card payment failed. Please try again."
                return _checkout_error(err)

            order.payment_status = "paid"
            db.session.add(Payment(
                order=order, provider="stripe", amount=order.total,
                status="succeeded",
                provider_ref=payment_result["reference"], raw=payment_result["raw"],
            ))
        else:  # cash / pay-at-store
            order.payment_status = "pending"
            db.session.add(Payment(order=order, provider="cash", amount=order.total, status="pending"))

        if order.payment_status == "paid":
            order.status = "confirmed"

        # Loyalty: 10 pts per $1 (SRS FR-9.1)
        if order.user:
            order.user.loyalty_points += int(float(order.total))

        if order.customer_email:
            try:
                from app.services.subscribers import ensure_subscriber
                ensure_subscriber(
                    order.customer_email,
                    store=store,
                    source="order",
                    ip_address=request.remote_addr,
                )
            except Exception:
                current_app.logger.warning(
                    "order subscriber add failed for %s",
                    order.customer_email,
                    exc_info=True,
                )

        db.session.commit()

        from app.services.order_sync import sync_order_integrations
        sync_order_integrations(order, payment_result=payment_result)

        # Notify the customer via THIS store's own SMS/email integrations.
        from app.services.notifications import notify_order_event, notify_store_new_order
        notify_order_event(order, order.status)
        notify_store_new_order(order)

        cartlib.clear()
        session.pop("checkout_draft", None)
        session.pop("schedule_at", None)
        session["last_order_id"] = order.id
        flash(f"Order {order.number} placed! 🎉", "success")
        return redirect("/order-confirmed")

    # GET | restore a failed submit, or show defaults
    draft = session.pop("checkout_draft", None)
    return _render_checkout(store, draft)


@bp.post("/checkout/payment-intent")
def checkout_payment_intent():
    """Create a Stripe PaymentIntent for Elements confirmation before order submit."""
    store = get_current_store()
    if not store or not fulfillment_available(store):
        return jsonify(ok=False, error="Delivery and pickup are unavailable at this location."), 400
    payload = request.get_json(silent=True) or {}
    try:
        amount = float(payload.get("amount") or request.form.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        return jsonify(ok=False, error="Invalid order total"), 400

    email = _checkout_email(payload.get("email"))
    if not email:
        return jsonify(
            ok=False,
            error="Please enter a valid email address before paying with your card.",
        ), 400

    result = create_payment_intent(
        store, amount,
        metadata={"store": store.slug, "checkout": "1", "customer_email": email[:100]},
    )
    if result["status"] == "failed":
        err = (result.get("raw") or {}).get("error") or "Could not start card payment"
        return jsonify(ok=False, error=err), 400

    return jsonify(
        ok=True,
        demo=bool((result.get("raw") or {}).get("demo")),
        client_secret=result.get("client_secret"),
        reference=result.get("reference"),
        mode=stripe_checkout_mode(store),
    )


@bp.get("/order-confirmed")
def order_confirmed():
    order = Order.query.get(session.get("last_order_id")) if session.get("last_order_id") else None
    if not order:
        return redirect("/")
    return render_template("checkout/order-confirmed.html", order=order)
