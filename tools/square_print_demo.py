"""Generate kitchen + cashier print preview HTML from real Square order builder."""
import os
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.integrations.square_gateway import build_square_order

STORE = SimpleNamespace(
    slug="lancaster",
    name="OK Smashed Burger — Lancaster",
    avg_prep_minutes=15,
    address_line="3517 Lancaster Ave, Philadelphia, PA 19104-4915",
    phone="(215) 948-9965",
)

ORDER = SimpleNamespace(
    number="PI7q",
    currency="USD",
    order_type="delivery",
    customer_name="Muhammad (Test)",
    customer_email="test@example.com",
    customer_phone="+12155550199",
    address="3517 Lancaster Ave, Philadelphia, PA 19104",
    address_line1="3517 Lancaster Ave",
    address_line2="",
    address_city="Philadelphia",
    address_state="PA",
    address_zip="19104",
    payment_method="card",
    payment_status="paid",
    notes=(
        "Hey, 3517 Lancaster Ave, 19104, Location Staff its me Muhammad — "
        "this is a test order from our website. Please don't take it serious."
    ),
    subtotal=Decimal("1.80"),
    tax=Decimal("0.14"),
    delivery_fee=Decimal("0.01"),
    tip=Decimal("0.02"),
    discount=Decimal("0"),
    gift_card_applied=Decimal("0"),
    total=Decimal("1.97"),
    scheduled_for=None,
    items=[
        SimpleNamespace(
            name="Combo #1",
            qty=2,
            unit_price=Decimal("0.90"),
            options={
                "variant": "Single",
                "addons": [
                    {"name": "Patty", "price": 0.10, "qty": 2},
                    {"name": "Crispy Cheddar Cheese", "price": 0.10, "qty": 1},
                    {"name": "OK Sauce", "price": 0.10, "qty": 1},
                    {"name": "American Cheese", "price": 0.10, "qty": 1},
                    {"name": "Jalapeno", "price": 0.10, "qty": 1},
                    {"name": "Smoked Beef Bacon", "price": 0.10, "qty": 1},
                    {"name": "Fried Shallot/Fried Onion", "price": 0.10, "qty": 1},
                ],
            },
        )
    ],
)


def _cents(c):
    return float(c or 0) / 100.0


def _money(v):
    return "$%.2f" % float(v)


def _build_payload():
    with patch("app.integrations.square_gateway.store_square_config", return_value={"location_id": "LDEMO"}):
        body, _, _ = build_square_order(ORDER, STORE)
    return body


def _kitchen_html(body, now):
    lines = []
    header = (body.get("note") or "").split("\n")
    for h in header:
        if h.strip():
            lines.append(("header", h.strip()))
    fulfill = ((body.get("fulfillments") or [{}])[0].get("pickup_details") or {}).get("note") or ""
    for h in fulfill.split("\n"):
        if h.strip():
            lines.append(("header", h.strip()))

    for li in body.get("line_items") or []:
        qty = int(float(li.get("quantity", "1")))
        name = li.get("name", "Item")
        lines.append(("item", "%d x %s" % (qty, name)))
        for mod in li.get("modifiers") or []:
            lines.append(("mod", mod.get("name", "")))
        note = (li.get("note") or "").strip()
        if note:
            lines.append(("note", '"%s"' % note))

    return lines


def _cashier_html(body, now):
    rows = []
    subtotal = 0.0
    for li in body.get("line_items") or []:
        qty = int(float(li.get("quantity", "1")))
        unit = _cents((li.get("base_price_money") or {}).get("amount"))
        line_total = unit * qty
        subtotal += line_total
        name = li.get("name", "Item")
        rows.append({
            "name": name if qty == 1 else "%s x %d" % (name, qty),
            "detail": _money(unit) + (" total" if qty == 1 and " x" in name else " each"),
            "total": _money(line_total),
            "mods": [m.get("name", "") for m in (li.get("modifiers") or [])],
            "note": (li.get("note") or "").strip(),
        })

    return {
        "rows": rows,
        "total": _money(ORDER.total),
        "ticket": body.get("ticket_name") or ORDER.number,
        "header_note": body.get("note") or "",
    }


def render_html():
    body = _build_payload()
    now = datetime.now().strftime("%B %d, %Y  %I:%M %p")
    kitchen = _kitchen_html(body, now)
    cashier = _cashier_html(body, now)

    kitchen_lines = "\n".join(
        '<div class="line %s">%s</div>' % (cls, text.replace("<", "&lt;"))
        for cls, text in kitchen
    )
    cashier_items = []
    for row in cashier["rows"]:
        cashier_items.append(
            '<div class="item-row"><div class="item-top"><span class="item-name">%s</span>'
            '<span class="item-price">%s</span></div>'
            '<div class="item-sub muted">%s</div>' % (row["name"], row["total"], row["detail"])
        )
        for m in row["mods"]:
            cashier_items.append('<div class="mod">%s</div>' % m)
        if row["note"]:
            cashier_items.append('<div class="note">%s</div>' % row["note"])
        cashier_items.append("</div>")

    header_note = "<br>".join(
        line.replace("<", "&lt;") for line in cashier["header_note"].split("\n") if line.strip()
    )

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Square Print Demo — Kitchen vs Cashier</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: Georgia, "Times New Roman", serif; background: #e8e4dc; margin: 0; padding: 24px; color: #111; }
  h1 { font-family: system-ui, sans-serif; text-align: center; font-size: 1.25rem; margin: 0 0 8px; }
  .sub { text-align: center; font-family: system-ui, sans-serif; font-size: 0.85rem; color: #555; margin-bottom: 28px; }
  .wrap { display: flex; flex-wrap: wrap; gap: 32px; justify-content: center; align-items: flex-start; }
  .col { text-align: center; }
  .label { font-family: system-ui, sans-serif; font-weight: 700; font-size: 0.75rem; letter-spacing: .08em; text-transform: uppercase; color: #666; margin-bottom: 10px; }
  .printer { font-family: system-ui, sans-serif; font-size: 0.7rem; color: #888; margin-bottom: 6px; }
  .ticket {
    width: 280px; background: #faf8f2; padding: 18px 16px 22px;
    box-shadow: 0 4px 24px rgba(0,0,0,.18); text-align: left;
    font-size: 13px; line-height: 1.35; border: 1px solid #d8d4cc;
  }
  .ticket.kitchen { font-size: 14px; }
  .ticket.cashier { font-size: 12.5px; }
  .big { font-size: 22px; font-weight: 700; text-align: center; margin: 4px 0 2px; font-family: system-ui, sans-serif; }
  .center { text-align: center; }
  .muted { color: #444; font-size: 12px; }
  .biz { text-align: center; font-weight: 700; font-size: 11px; line-height: 1.45; margin-bottom: 8px; }
  .dash { border-top: 1px dashed #999; margin: 10px 0; }
  .line.header { font-weight: 700; margin-top: 6px; }
  .line.item { font-weight: 700; margin-top: 10px; font-size: 15px; }
  .line.mod, .mod { padding-left: 10px; font-size: 12.5px; margin-top: 2px; }
  .line.note, .note { padding-left: 10px; font-style: italic; font-size: 11.5px; margin-top: 4px; color: #333; }
  .item-row { margin-top: 8px; }
  .item-top { display: flex; justify-content: space-between; gap: 8px; font-weight: 600; }
  .item-name { flex: 1; }
  .item-price { white-space: nowrap; }
  .item-sub { font-size: 11px; }
  .totals { margin-top: 12px; }
  .totals div { display: flex; justify-content: space-between; margin: 3px 0; }
  .totals .grand { font-weight: 800; font-size: 15px; border-top: 1px solid #333; padding-top: 6px; margin-top: 6px; }
  .badge { display: inline-block; background: #141414; color: #ffc72c; font-family: system-ui,sans-serif; font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px; margin-top: 14px; }
  .ok { color: #1a7f37; font-family: system-ui,sans-serif; font-size: 11px; margin-top: 8px; }
  .no { color: #c0392b; font-family: system-ui,sans-serif; font-size: 11px; margin-top: 4px; text-decoration: line-through; opacity: .7; }
</style>
</head>
<body>
<h1>Square Print Preview (after fix)</h1>
<p class="sub">Same test order PI7q — built from live <code>build_square_order()</code> code</p>
<div class="wrap">
  <div class="col">
    <div class="label">Kitchen ticket</div>
    <div class="printer">Star SP700</div>
    <div class="ticket kitchen">
      <div class="big">Receipt #%s</div>
      <div class="center muted">%s</div>
      <div class="dash"></div>
      %s
      <div class="dash"></div>
      <div class="ok">✓ No prices / no subtotal / no tax / no total</div>
      <div class="no">✗ No "kitchen profile" footer (set in Square → Printers)</div>
    </div>
    <span class="badge">KITCHEN</span>
  </div>
  <div class="col">
    <div class="label">Cashier receipt</div>
    <div class="printer">Star TSP100</div>
    <div class="ticket cashier">
      <div class="center muted">%s</div>
      <div class="center muted">Ticket: Receipt #%s</div>
      <div class="dash"></div>
      <div class="muted" style="font-size:11px;margin-bottom:8px">%s</div>
      %s
      <div class="dash"></div>
      <div class="totals">
        <div class="no"><span>Subtotal</span><span>hidden</span></div>
        <div class="no"><span>Sales Tax</span><span>hidden</span></div>
        <div class="no"><span>Delivery</span><span>hidden</span></div>
        <div class="no"><span>Tip</span><span>hidden</span></div>
        <div class="grand"><span>Total</span><span>%s</span></div>
        <div><span>Debit/Credit</span><span>%s</span></div>
      </div>
      <div class="ok" style="margin-top:10px">✓ No store address header · tax/delivery/tip in item price</div>
    </div>
    <span class="badge">CASHIER</span>
  </div>
</div>
</body>
</html>""" % (
        ORDER.number,
        now,
        kitchen_lines,
        now,
        cashier["ticket"],
        header_note,
        "\n".join(cashier_items),
        cashier["total"],
        cashier["total"],
    )


def main():
    out = os.path.join(os.path.dirname(__file__), "square_print_demo.html")
    html = render_html()
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote:", out)
    return out


if __name__ == "__main__":
    main()
