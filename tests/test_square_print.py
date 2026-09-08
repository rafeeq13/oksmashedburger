"""Square ticket/receipt payload — kitchen vs cashier print rules."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.square_gateway import build_square_order
from app.services.order_details import square_line_item_modifiers

_SQUARE_CFG = {"location_id": "LTEST123"}


def _order(**kw):
    defaults = {
        "number": "OK-9999",
        "currency": "USD",
        "order_type": "delivery",
        "customer_name": "Test Guest",
        "customer_email": "test@example.com",
        "customer_phone": "+12155550100",
        "payment_method": "card",
        "address": "3517 Lancaster Ave",
        "address_line1": "3517 Lancaster Ave",
        "address_line2": "",
        "address_city": "Philadelphia",
        "address_state": "PA",
        "address_zip": "19104",
        "scheduled_for": None,
        "notes": "Please ring doorbell",
        "subtotal": Decimal("1.80"),
        "tax": Decimal("0.14"),
        "delivery_fee": Decimal("0.01"),
        "tip": Decimal("0.02"),
        "discount": Decimal("0"),
        "gift_card_applied": Decimal("0"),
        "total": Decimal("1.97"),
        "items": [],
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _item(**kw):
    defaults = {
        "name": "Combo #1",
        "qty": 2,
        "unit_price": Decimal("0.90"),
        "options": {
            "variant": "Single",
            "addons": [
                {"name": "Patty", "price": 0.10, "qty": 2},
                {"name": "OK Sauce", "price": 0.10, "qty": 1},
            ],
            "notes": "Extra crispy",
        },
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_square_modifiers_are_structured_without_prices():
    mods = square_line_item_modifiers(_item(), "USD")
    assert len(mods) == 2
    assert mods[0]["name"] == "+ Patty x2"
    assert mods[0]["base_price_money"]["amount"] == 0
    assert mods[1]["name"] == "+ OK Sauce"


@patch("app.integrations.square_gateway.store_square_config", return_value=_SQUARE_CFG)
def test_square_order_has_no_service_charges(_mock_cfg):
    order = _order(items=[_item()])
    store = SimpleNamespace(slug="test", avg_prep_minutes=15)
    body, _, _ = build_square_order(order, store)
    assert not body.get("service_charges")


@patch("app.integrations.square_gateway.store_square_config", return_value=_SQUARE_CFG)
def test_square_order_embeds_tax_delivery_tip_in_line_items(_mock_cfg):
    order = _order(items=[_item()])
    store = SimpleNamespace(slug="test", avg_prep_minutes=15)
    body, _, _ = build_square_order(order, store)
    li = body["line_items"][0]
    # 180¢ items + 17¢ (tax+delivery+tip) = 197¢ total on one line (qty collapsed)
    assert li["quantity"] == "1"
    assert li["base_price_money"]["amount"] == 197
    assert "modifiers" in li
    assert li["note"] == "Extra crispy"


@patch("app.integrations.square_gateway.store_square_config", return_value=_SQUARE_CFG)
def test_square_order_note_has_no_delivery_address(_mock_cfg):
    order = _order(items=[_item()])
    store = SimpleNamespace(slug="test", avg_prep_minutes=15)
    body, _, _ = build_square_order(order, store)
    assert "3517 Lancaster" not in (body.get("note") or "")
    fulfillment_note = body["fulfillments"][0]["pickup_details"].get("note") or ""
    assert "DELIVERY" in fulfillment_note
    assert "3517 Lancaster" in fulfillment_note


@patch("app.integrations.square_gateway.store_square_config", return_value=_SQUARE_CFG)
def test_square_line_item_name_includes_variant(_mock_cfg):
    order = _order(items=[_item()])
    store = SimpleNamespace(slug="test", avg_prep_minutes=15)
    body, _, _ = build_square_order(order, store)
    assert "Combo #1 - Single" in body["line_items"][0]["name"]
