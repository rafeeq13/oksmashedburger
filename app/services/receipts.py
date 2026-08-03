"""Generate a printable, branded PDF receipt for an order (fpdf2, pure-Python)."""
import os

from fpdf import FPDF

BRAND = "OK Smashed Burger"
JET = (20, 20, 20)
SLATE = (107, 107, 107)
MUTE = (140, 140, 140)
YELLOW = (255, 199, 44)
AMBER = (224, 162, 0)
GREEN = (46, 125, 50)
LINE = (226, 226, 226)
SOFT = (255, 248, 227)     # soft yellow tint for table header / zebra

LOGO = os.path.join(os.path.dirname(__file__), "..", "static", "img", "logo.png")


def _s(text):
    """Core PDF fonts are latin-1 only — drop anything they can't encode."""
    return str(text if text is not None else "").encode("latin-1", "replace").decode("latin-1")


def _money(v):
    return f"${float(v or 0):.2f}"


def build_receipt_pdf(order):
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 14, 18)
    pdf.add_page()
    X = 18
    W = pdf.w - 36  # printable width

    # ── Header: logo + RECEIPT / order / date ─────────────────
    logo_bottom = 14
    try:
        if os.path.exists(LOGO):
            lw = 21
            pdf.image(LOGO, x=X, y=13, w=lw)
            logo_bottom = 13 + lw * 275.0 / 210.0   # keep aspect ratio
    except Exception:
        pass

    pdf.set_xy(X, 15)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(*JET)
    pdf.cell(W, 11, "RECEIPT", align="R")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*SLATE)
    pdf.set_xy(X, 28)
    pdf.cell(W, 5.5, _s(f"Order  {order.number}"), align="R")
    pdf.set_xy(X, 33.5)
    pdf.cell(W, 5.5, _s(order.created_at.strftime("%b %d, %Y  \xb7  %I:%M %p")), align="R")

    y = max(logo_bottom, 41) + 2
    pdf.set_draw_color(*YELLOW)
    pdf.set_line_width(1.4)
    pdf.line(X, y, X + W, y)
    pdf.set_y(y + 6)

    # ── From / Bill-to ────────────────────────────────────────
    store = order.store
    left = [store.name if store else BRAND]
    if store:
        if store.full_address:
            left.append(store.full_address)
        if store.phone:
            left.append(store.phone)
    right = [order.customer_name or "Guest"]
    if order.customer_email:
        right.append(order.customer_email)
    if order.customer_phone:
        right.append(order.customer_phone)
    if order.address:
        right.append(order.address)

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*MUTE)
    pdf.cell(W / 2, 5, "FROM")
    pdf.cell(W / 2, 5, "BILL TO")
    pdf.ln(5.5)
    for i in range(max(len(left), len(right))):
        first = i == 0
        pdf.set_font("Helvetica", "B" if first else "", 11 if first else 9.5)
        pdf.set_text_color(*(JET if first else SLATE))
        pdf.cell(W / 2, 5, _s(left[i]) if i < len(left) else "")
        pdf.cell(W / 2, 5, _s(right[i]) if i < len(right) else "")
        pdf.ln(5)

    # ── Order meta chips row ──────────────────────────────────
    pdf.ln(2)
    meta = [("Type", order.order_type.title()),
            ("Status", order.status.replace("_", " ").title()),
            ("Payment", (order.payment_method or "Card").title() + " \xb7 " + order.payment_status.title())]
    if getattr(order, "scheduled_for", None):
        meta.append(("Scheduled", order.scheduled_for.strftime("%b %d, %I:%M %p")))
    for label, val in meta:
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*MUTE)
        pdf.cell(2, 5, "")
        w_lbl = pdf.get_string_width(label.upper()) + 2
        pdf.cell(w_lbl, 5, _s(label.upper()))
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*JET)
        w_val = pdf.get_string_width(_s(val)) + 5
        pdf.cell(w_val, 5, _s(val))
    pdf.ln(9)

    # ── Items table ───────────────────────────────────────────
    pdf.set_fill_color(*JET)
    pdf.set_text_color(*YELLOW)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(W * 0.10, 7.5, "  QTY", fill=True)
    pdf.cell(W * 0.68, 7.5, "ITEM", fill=True)
    pdf.cell(W * 0.22, 7.5, "AMOUNT  ", align="R", fill=True)
    pdf.ln(7.5)

    zebra = False
    for it in order.items:
        opts = it.options or {}
        detail = []
        if opts.get("variant"):
            v = opts["variant"]
            vd = opts.get("variant_delta")
            if vd:
                v += f" ({'+' if float(vd) >= 0 else '-'}{_money(abs(float(vd)))})"
            detail.append(v)
        for a in opts.get("addons") or []:
            detail.append(f"+ {a.get('name', '')}  (+{_money(a.get('price', 0))})")
        if opts.get("notes"):
            detail.append(f"Note: {opts['notes']}")

        row_h = 7 + 4.6 * len(detail)
        if zebra:
            pdf.set_fill_color(250, 250, 248)
            pdf.rect(X, pdf.get_y(), W, row_h, "F")
        zebra = not zebra

        top = pdf.get_y()
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*JET)
        pdf.cell(W * 0.10, 7, _s("  " + str(it.qty)))
        pdf.cell(W * 0.68, 7, _s(it.name))
        pdf.cell(W * 0.22, 7, _money(it.line_total) + "  ", align="R")
        pdf.ln(7)
        for d in detail:
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*SLATE)
            pdf.cell(W * 0.10, 4.6, "")
            pdf.cell(W * 0.90, 4.6, _s(d))
            pdf.ln(4.6)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.2)
        pdf.line(X, pdf.get_y(), X + W, pdf.get_y())

    pdf.ln(4)

    # ── Totals ────────────────────────────────────────────────
    def row(label, value, kind="normal"):
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(W * 0.55, 6.5, "")
        pdf.set_text_color(*SLATE)
        pdf.cell(W * 0.25, 6.5, _s(label), align="R")
        pdf.set_text_color(*(GREEN if kind == "discount" else JET))
        pdf.cell(W * 0.20, 6.5, _s(value) + "  ", align="R")
        pdf.ln(6.5)

    row("Subtotal", _money(order.subtotal))
    if order.discount:
        lbl = "Discount" + (f" ({order.coupon_code})" if order.coupon_code else "")
        row(lbl, "-" + _money(order.discount), "discount")
    row("Tax", _money(order.tax))
    if order.delivery_fee:
        row("Delivery", _money(order.delivery_fee))
    if order.tip:
        row("Tip", _money(order.tip))
    if order.gift_card_applied:
        row("Gift card", "-" + _money(order.gift_card_applied), "discount")

    # highlighted TOTAL bar (right half)
    pdf.ln(1)
    ty = pdf.get_y()
    bx = X + W * 0.55
    bw = W * 0.45
    pdf.set_fill_color(*JET)
    pdf.rect(bx, ty, bw, 12, "F")
    pdf.set_xy(bx, ty)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(bw * 0.45, 12, "  TOTAL", align="L")
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*YELLOW)
    pdf.cell(bw * 0.55, 12, _money(order.total) + "  ", align="R")
    pdf.ln(16)

    # ── Footer ────────────────────────────────────────────────
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    pdf.line(X, pdf.get_y(), X + W, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*JET)
    pdf.cell(W, 6, _s("Thank you for your order!"), align="C")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*SLATE)
    contact = store.phone if (store and store.phone) else ""
    line2 = f"{BRAND}" + (f"  \xb7  {store.name}" if store else "") + (f"  \xb7  {contact}" if contact else "")
    pdf.cell(W, 5, _s(line2), align="C")
    pdf.ln(5)
    pdf.set_text_color(*MUTE)
    pdf.cell(W, 5, _s("Rewards points are applied automatically to member accounts. "
                      "Questions? Reply to your confirmation email."), align="C")
    return bytes(pdf.output())
