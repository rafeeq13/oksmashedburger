"""Checkout → order creation → per-store payment → confirmation."""
from decimal import Decimal
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, session, flash

from app.extensions import db
from app import cart as cartlib
from app.helpers import get_current_store
from app.auth import current_user
from app.models.order import Order, OrderItem, Payment
from app.models.promo import Coupon, GiftCard
from app.integrations.stripe_gateway import charge, store_stripe_config, is_connected

bp = Blueprint("checkout", __name__)


@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    store = get_current_store()
    if not cartlib.get_cart():
        return redirect("/menu")

    if request.method == "POST":
        order_type = request.form.get("order_type", "delivery")
        method = request.form.get("payment_method", "card")
        tip = request.form.get("tip", type=float) or 0.0

        # ── Open/closed + scheduling enforcement ─────────────────────
        fulfillment = request.form.get("fulfillment", "asap")
        scheduled_for = None
        if fulfillment == "scheduled":
            if not (store and store.scheduling_open):
                flash("Scheduled ordering isn't available for this store right now.", "error")
                return redirect("/checkout")
            try:
                scheduled_for = datetime.strptime(request.form.get("scheduled_for", ""), "%Y-%m-%dT%H:%M")
            except (ValueError, TypeError):
                flash("Please choose a valid date and time for your scheduled order.", "error")
                return redirect("/checkout")
            if scheduled_for <= datetime.now():
                flash("Your scheduled time must be in the future.", "error")
                return redirect("/checkout")
            if not store.is_open_at(scheduled_for):
                flash(f"{store.name} isn't open at that time — please pick a slot within opening hours "
                      f"({store.today_hours} today).", "error")
                return redirect("/checkout")
        else:  # ASAP
            if not (store and store.open_now):
                flash(f"{store.name if store else 'This store'} is closed for immediate orders — "
                      "please schedule your order for later.", "error")
                return redirect("/checkout")

        # A delivery order without an address is undeliverable, and the browser
        # `required` attribute is not a guarantee — it is trivially bypassed.
        address = request.form.get("address", "").strip()
        if order_type == "delivery" and not address:
            flash("Please enter a delivery address.", "error")
            return redirect("/checkout")

        s = cartlib.summary(store, tip=tip, order_type=order_type)

        order = Order(
            store=store, user=current_user(), order_type=order_type,
            scheduled_for=scheduled_for,
            customer_name=request.form.get("name", "").strip(),
            customer_email=request.form.get("email", "").strip(),
            customer_phone=request.form.get("phone", "").strip(),
            address=address,
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

        # Payment — routed through THIS store's own Stripe account.
        if method == "card":
            result = charge(store, s["total"], metadata={"order": order.number, "store": store.slug})
            order.payment_status = "paid" if result["status"] == "succeeded" else "pending"
            db.session.add(Payment(
                order=order, provider="stripe", amount=order.total,
                status="succeeded" if result["status"] == "succeeded" else result["status"],
                provider_ref=result["reference"], raw=result["raw"],
            ))
        else:  # cash / pay-at-store
            order.payment_status = "pending"
            db.session.add(Payment(order=order, provider="cash", amount=order.total, status="pending"))

        if order.payment_status == "paid":
            order.status = "confirmed"

        # Loyalty: 10 pts per $1 (SRS FR-9.1)
        if order.user:
            order.user.loyalty_points += int(float(order.total))

        db.session.commit()

        # Notify the customer via THIS store's own SMS/email integrations.
        from app.services.notifications import notify_order_event
        notify_order_event(order, order.status)

        cartlib.clear()
        session["last_order_id"] = order.id
        flash(f"Order {order.number} placed! 🎉", "success")
        return redirect("/order-confirmed")

    # GET — price for the customer's current Delivery/Pickup choice
    ot = session.get("order_type", "delivery")
    s = cartlib.summary(store, order_type=ot)
    s_delivery = s if ot == "delivery" else cartlib.summary(store, order_type="delivery")
    s_pickup = s if ot == "pickup" else cartlib.summary(store, order_type="pickup")
    u = current_user()
    default_address = None
    if u:
        from app.models.address import UserAddress
        default_address = (UserAddress.query.filter_by(user_id=u.id, is_default=True).first()
                           or UserAddress.query.filter_by(user_id=u.id).first())
    now = datetime.now()
    return render_template(
        "checkout/checkout.html", store=store, summary=s, user=u,
        default_address=default_address,
        min_schedule=(now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"),
        default_schedule=(now + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M"),
        stripe_pub_key=store_stripe_config(store).get("publishable_key", ""),
        stripe_connected=is_connected(store),
        checkout_delivery_fee=s_delivery["delivery_fee"],
        checkout_delivery_free=bool(s_delivery["promo"].get("delivery_discount")),
        checkout_total_delivery=s_delivery["total"],
        checkout_total_pickup=s_pickup["total"],
    )


@bp.get("/order-confirmed")
def order_confirmed():
    order = Order.query.get(session.get("last_order_id")) if session.get("last_order_id") else None
    if not order:
        return redirect("/")
    return render_template("checkout/order-confirmed.html", order=order)
