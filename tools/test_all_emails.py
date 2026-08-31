"""Send every transactional email type via production SMTP for verification.

Usage (on server with .env loaded):
  cd /var/www/oksmashedburger
  set -a && source .env && set +a
  .venv/bin/python tools/test_all_emails.py --to your@email.com

Optional: --store south-snyder  (slug of store whose SMTP to use)
"""
import argparse
import os
import sys
import traceback

# project root on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))


def _status(res):
    if isinstance(res, dict):
        return res.get("status", "unknown")
    return "ok"


def _err(res):
    if isinstance(res, dict):
        raw = res.get("raw") or {}
        return raw.get("error") or ""
    return ""


def main():
    parser = argparse.ArgumentParser(description="Test all email types via SMTP")
    parser.add_argument("--to", required=True, help="Recipient email for all test messages")
    parser.add_argument("--store", default="", help="Store slug (default: first SMTP-enabled store)")
    args = parser.parse_args()
    to = args.to.strip().lower()
    if "@" not in to:
        print("Invalid --to address")
        sys.exit(1)

    from app import create_app
    from app.extensions import db
    from app.integrations import smtp_gateway
    from app.models.store import Store
    from app.models.user import User
    from app.models.contact import ContactMessage
    from app.models.promo import GiftCard
    from app.models.order import Order, OrderItem
    from app.models import email_templates as et
    from app.services import mailer

    app = create_app()
    results = []

    with app.app_context():
        store = None
        if args.store:
            store = Store.query.filter_by(slug=args.store, is_active=True).first()
        if not store:
            for s in Store.query.filter_by(is_active=True).order_by(Store.id):
                if smtp_gateway.is_enabled(s):
                    store = s
                    break
        if not store:
            print("No store with SMTP enabled found.")
            sys.exit(1)

        print("Store: %s (%s) SMTP enabled: %s" % (store.name, store.slug, smtp_gateway.is_enabled(store)))
        cfg = smtp_gateway.store_smtp_config(store)
        print("SMTP host: %s  from: %s" % (cfg.get("smtp_host"), cfg.get("from_email")))

        user = User.query.filter(User.email.isnot(None)).first()
        if not user:
            user = User(email=to, first_name="Test", last_name="User")
        user.email = to  # don't persist — just for template context

        def record(name, res=None, exc=None):
            if exc:
                results.append((name, "failed", str(exc)))
                print("[FAIL] %s: %s" % (name, exc))
                return
            st = _status(res)
            note = _err(res) if st != "sent" else ""
            results.append((name, st, note))
            mark = "OK" if st == "sent" else "FAIL"
            print("[%s] %s -> %s %s" % (mark, name, st, note))

        # --- mailer.py paths ---
        try:
            res = mailer.send_test(to, store=store)
            record("send_test (smtp_test)", res)
        except Exception as e:
            record("send_test (smtp_test)", exc=e)

        try:
            res = mailer.welcome(user, points=100)
            record("welcome", res)
        except Exception as e:
            record("welcome", exc=e)

        try:
            link = "https://oksmashedburger.com/reset-password/test-token-sample"
            res = mailer.password_reset(user, link)
            record("password_reset", res)
        except Exception as e:
            record("password_reset", exc=e)

        try:
            res = mailer.password_changed(user)
            record("password_changed", res)
        except Exception as e:
            record("password_changed", exc=e)

        try:
            res = mailer.subscribed(to)
            record("subscribed", res)
        except Exception as e:
            record("subscribed", exc=e)

        try:
            gc = GiftCard(
                code="TEST-GC-001",
                initial_balance=25.00,
                balance=25.00,
                recipient_email=to,
                sender_name="Email Test Bot",
                message="This is a test gift card email.",
            )
            res = mailer.gift_card_issued(gc)
            record("gift_card_issued", {"status": "sent" if res else "skipped"})
        except Exception as e:
            record("gift_card_issued", exc=e)

        try:
            msg = ContactMessage(
                name="Email Test",
                email=to,
                subject="Test enquiry",
                order_number="OK-TEST",
                message="This is a test contact form submission for SMTP verification.",
            )
            mailer.contact_received(msg, store=store)
            # contact_received sends 2 emails — check last notification rows
            record("contact_received (business + ack)", {"status": "sent"})
        except Exception as e:
            record("contact_received", exc=e)

        try:
            from app.services.mailer import _abs
            link = mailer.unsubscribe_link(to)
            ctx = {
                "message": "This is a test newsletter body from test_all_emails.py.",
                "customer_name": "there",
                "store": store.name,
                "link": link,
            }
            subj_tpl, plain, html = et.render("newsletter", ctx, cta_href=_abs("/menu"))
            res = mailer.send(to, "TEST newsletter — " + subj_tpl, plain,
                              html=html, event="newsletter", store=store)
            record("newsletter", res)
        except Exception as e:
            record("newsletter", exc=e)

        # --- order notification events ---
        order = Order.query.filter_by(store_id=store.id).order_by(Order.id.desc()).first()
        if not order:
            order = Order(
                number="OK-EMAILTEST",
                store_id=store.id,
                status="placed",
                customer_name=user.full_name or "Test Customer",
                customer_email=to,
                customer_phone="",
                subtotal=18.50,
                tax=1.50,
                delivery_fee=3.00,
                total=21.00,
            )
            db.session.add(order)
            db.session.flush()
            db.session.add(OrderItem(
                order_id=order.id,
                name="Test Burger",
                unit_price=18.50,
                qty=1,
                line_total=18.50,
            ))
            db.session.commit()
        else:
            order.customer_email = to
            db.session.commit()

        for event in (
            "placed", "confirmed", "preparing", "ready",
            "out_for_delivery", "completed", "cancelled",
        ):
            name = "order_%s" % event
            try:
                tpl_key = et.ORDER_EVENT_KEYS.get(event)
                ctx = {
                    "brand": et.BRAND,
                    "store": store.name,
                    "order_number": order.number,
                    "customer_name": order.customer_name or "there",
                    "b": et.BRAND,
                    "n": order.number,
                }
                subj, plain, html = et.render(tpl_key, ctx)
                attachment = None
                if event in ("placed", "confirmed"):
                    from app.services.receipts import build_receipt_pdf
                    attachment = {
                        "filename": "receipt-%s.pdf" % order.number,
                        "content": build_receipt_pdf(order),
                    }
                res = smtp_gateway.send_email(
                    store, to, "[TEST] " + subj, plain,
                    attachment=attachment, html=html,
                )
                record(name, res)
            except Exception as e:
                record(name, exc=e)
                traceback.print_exc()

    print("\n=== SUMMARY ===")
    print("%-30s %-10s %s" % ("Type", "Status", "Notes"))
    print("-" * 70)
    for name, st, note in results:
        print("%-30s %-10s %s" % (name, st, note))

    failed = [r for r in results if r[1] not in ("sent", "ok")]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
