"""Tests for delivery zone matching."""
from types import SimpleNamespace

from app.services.delivery_zones import match_delivery_zone, normalize_zip, haversine_miles


def _store(**kw):
    defaults = dict(
        name="Center City",
        latitude=39.9526,
        longitude=-75.1652,
        min_order_amount=10,
        delivery_zones=[],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _zone(name, zip_codes=None, radius=3.0, fee=3.99, min_order=10, active=True):
    return SimpleNamespace(
        id=1,
        name=name,
        zip_codes=zip_codes or [],
        radius_miles=radius,
        delivery_fee=fee,
        min_order=min_order,
        est_minutes=30,
        is_active=active,
    )


def test_normalize_zip():
    assert normalize_zip("19102") == "19102"
    assert normalize_zip("19102-1234") == "19102"


def test_haversine_miles_same_point():
    assert haversine_miles(39.95, -75.16, 39.95, -75.16) == 0.0


def test_match_by_zip_code():
    store = _store(delivery_zones=[
        _zone("Local", zip_codes=["19102"], radius=1.5, fee=9.99),
        _zone("Standard", zip_codes=["19103"], radius=3.0, fee=3.99),
    ])
    hit = match_delivery_zone(store, zip_code="19103")
    assert hit["in_zone"] is True
    assert hit["zone_name"] == "Standard"
    assert hit["delivery_fee"] == 3.99


def test_out_of_zone_zip():
    store = _store(delivery_zones=[
        _zone("Local", zip_codes=["19102"], radius=1.5, fee=9.99),
    ])
    hit = match_delivery_zone(store, zip_code="90210", line1="123 Main St", city="Beverly Hills", state="CA")
    assert hit["in_zone"] is False
    assert "123 Main St" in hit["message"]
    assert "can't deliver" in hit["message"].lower()


def test_match_by_distance_when_no_zip_list():
    store = _store(delivery_zones=[
        _zone("Standard", zip_codes=[], radius=3.0, fee=4.99),
        _zone("Extended", zip_codes=[], radius=6.0, fee=6.99),
    ])
    # ~1 mile north of store
    hit = match_delivery_zone(store, zip_code="", lat=39.967, lng=-75.1652)
    assert hit["in_zone"] is True
    assert hit["delivery_fee"] == 4.99
