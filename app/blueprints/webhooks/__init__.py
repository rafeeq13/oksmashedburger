"""Inbound webhooks from Stripe, Square, Uber Direct, and Twilio."""
from flask import Blueprint, request, jsonify, abort

from app.extensions import db
from app.models.store import Store
from app.services import webhook_handlers as wh
from app.integrations.config import active_integration_config
from app.integrations.webhook_urls import resolve_webhook_url, store_webhook_key

bp = Blueprint("webhooks", __name__)


def _store_or_404(slug):
    store = Store.query.filter_by(slug=slug, is_active=True).first()
    if not store:
        abort(404)
    return store


def _resolve_store_key(key):
    """Slug, location number (7014), or name hint."""
    store = Store.query.filter_by(slug=key, is_active=True).first()
    if store:
        return store
    hint = (key or "").strip()
    if not hint:
        abort(404)
    for s in Store.query.filter_by(is_active=True).all():
        if store_webhook_key(s) == hint:
            return s
    from sqlalchemy import or_
    store = (
        Store.query.filter(
            Store.is_active.is_(True),
            or_(
                Store.address_line.ilike("%%%s%%" % hint),
                Store.slug.ilike("%%%s%%" % hint),
                Store.name.ilike("%%%s%%" % hint),
            ),
        )
        .first()
    )
    if store:
        return store
    abort(404)


def _stripe_handle(store):
    sig = request.headers.get("Stripe-Signature", "")
    payload = request.get_data()
    try:
        event = wh.parse_stripe_event(store, payload, sig)
    except Exception as exc:
        wh.log_event(store, "stripe", "signature_failed", status="failed", error=str(exc))
        db.session.commit()
        return jsonify(error=str(exc)), 400
    try:
        result = wh.handle_stripe(store, event if isinstance(event, dict) else event.to_dict())
    except Exception as exc:
        db.session.rollback()
        wh.log_event(store, "stripe", "handler_error", status="failed", error=str(exc))
        db.session.commit()
        return jsonify(error="handler failed"), 500
    return jsonify(result)


@bp.post("/webhooks/<store_key>/stripe")
def stripe_webhook_short(store_key):
    """Alias: /webhooks/7014/stripe"""
    return _stripe_handle(_resolve_store_key(store_key))


@bp.post("/webhooks/stripe/<store_slug>")
def stripe_webhook(store_slug):
    return _stripe_handle(_store_or_404(store_slug))


@bp.post("/webhooks/<store_key>/square")
def square_webhook_short(store_key):
    return square_webhook(_resolve_store_key(store_key).slug)


@bp.post("/webhooks/square/<store_slug>")
def square_webhook(store_slug):
    store = _store_or_404(store_slug)
    cfg = active_integration_config(store, "square")
    sig = request.headers.get("x-square-hmacsha256-signature", "")
    body = request.get_data()
    url = resolve_webhook_url(store, "square", request.url_root.rstrip("/"))
    if not wh.verify_square_signature(cfg.get("webhook_signature_key"), sig, url, body):
        wh.log_event(store, "square", "signature_failed", status="failed",
                      error="invalid signature")
        db.session.commit()
        return jsonify(error="invalid signature"), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = wh.handle_square(store, payload)
    except Exception as exc:
        db.session.rollback()
        wh.log_event(store, "square", "handler_error", status="failed", error=str(exc))
        db.session.commit()
        return jsonify(error="handler failed"), 500
    return jsonify(result)


@bp.post("/webhooks/<store_key>/uber")
def uber_webhook_short(store_key):
    return uber_webhook(_resolve_store_key(store_key).slug)


@bp.post("/webhooks/uber/<store_slug>")
def uber_webhook(store_slug):
    store = _store_or_404(store_slug)
    cfg = active_integration_config(store, "uber_direct")
    body = request.get_data()
    sig = request.headers.get("x-uber-signature", "") or request.headers.get("X-Uber-Signature", "")
    if cfg.get("webhook_secret") and not wh.verify_uber_signature(cfg.get("webhook_secret"), sig, body):
        wh.log_event(store, "uber_direct", "signature_failed", status="failed",
                      error="invalid signature")
        db.session.commit()
        return jsonify(error="invalid signature"), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = wh.handle_uber(store, payload)
    except Exception as exc:
        db.session.rollback()
        wh.log_event(store, "uber_direct", "handler_error", status="failed", error=str(exc))
        db.session.commit()
        return jsonify(error="handler failed"), 500
    return jsonify(result)


@bp.post("/webhooks/<store_key>/twilio")
def twilio_webhook_short(store_key):
    return twilio_webhook(_resolve_store_key(store_key).slug)


@bp.post("/webhooks/twilio/<store_slug>")
def twilio_webhook(store_slug):
    store = _store_or_404(store_slug)
    sig = request.headers.get("X-Twilio-Signature", "")
    url = resolve_webhook_url(store, "twilio", request.url_root.rstrip("/"))
    try:
        if not wh.verify_twilio_request(store, url, request.form, sig):
            wh.log_event(store, "twilio", "signature_failed", status="failed",
                          error="invalid signature")
            db.session.commit()
            return jsonify(error="invalid signature"), 403
    except Exception as exc:
        wh.log_event(store, "twilio", "signature_failed", status="failed", error=str(exc))
        db.session.commit()
        return jsonify(error=str(exc)), 400
    try:
        result = wh.handle_twilio(store, request.form)
    except Exception as exc:
        db.session.rollback()
        wh.log_event(store, "twilio", "handler_error", status="failed", error=str(exc))
        db.session.commit()
        return jsonify(error="handler failed"), 500
    return jsonify(result)


@bp.get("/webhooks/health")
def webhooks_health():
    return jsonify(ok=True)
