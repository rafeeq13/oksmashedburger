"""Promo banner config helpers."""
from app.services.promo_banners import (
    normalize_promo_banner,
    promo_banner_on_request,
    promo_banner_visible,
    promo_visit_popup_before_location,
    setting_key_for_store,
)
from app.services.promo_page_targets import page_id_for_request_path, promo_shown_on_path


class _FakeStore:
    slug = "north-philadelphia"


def test_setting_key_for_store():
    assert setting_key_for_store(None) == "promo_banner"
    assert setting_key_for_store(_FakeStore()) == "promo_banner__north-philadelphia"


def test_normalize_placement():
    cfg = normalize_promo_banner({"placement": "above_footer", "height": 999})
    assert cfg["placement"] == "above_footer"
    assert cfg["height"] == 220
    legacy = normalize_promo_banner({"placement": "above_header"})
    assert legacy["placement"] == "visit_popup"


def test_text_only_no_image():
    cfg = normalize_promo_banner({"use_image": False, "image": "", "text": "Hello"})
    assert cfg["use_image"] is False
    assert cfg["image"] == ""


def test_subscribe_field_colors():
    cfg = normalize_promo_banner(
        {
            "subscribe_border_color": "#ff00aa",
            "subscribe_input_color": "#111111",
        }
    )
    assert cfg["subscribe_border_color"] == "#ff00aa"
    assert cfg["subscribe_input_color"] == "#111111"
    bad = normalize_promo_banner({"subscribe_border_color": "red"})
    assert bad["subscribe_border_color"] == "#ffffff"


def test_popup_close_button():
    cfg = normalize_promo_banner({"popup_close_size": 99, "popup_close_color": "#222222"})
    assert cfg["popup_close_size"] == 56
    assert cfg["popup_close_color"] == "#222222"
    assert cfg["popup_close_bg_color"] == "#ffffff"


def test_show_pages_legacy_defaults_all():
    cfg = normalize_promo_banner({"enabled": True})
    assert "home" in cfg["show_pages"]
    assert "menu" in cfg["show_pages"]


def test_show_pages_empty_list_repairs_to_all():
    cfg = normalize_promo_banner({"enabled": True, "show_pages": []})
    assert "home" in cfg["show_pages"]
    assert promo_shown_on_path(cfg["show_pages"], "/") is True


def test_visit_popup_included_before_location_when_not_on_show_pages():
    cfg = normalize_promo_banner(
        {
            "enabled": True,
            "placement": "visit_popup",
            "use_image": True,
            "show_pages": ["menu"],
        }
    )
    feats = {"deals": True}
    assert promo_banner_visible(cfg, feats, "/") is False
    assert promo_visit_popup_before_location(cfg, feats, needs_location=True) is True
    assert promo_banner_on_request(cfg, feats, "/", needs_location=True) is True
    assert promo_visit_popup_before_location(cfg, feats, needs_location=False) is False


def test_promo_visible_respects_show_pages():
    cfg = normalize_promo_banner(
        {"enabled": True, "use_image": True, "show_pages": ["home"]}
    )
    feats = {"deals": True}
    assert promo_banner_visible(cfg, feats, "/") is True
    assert promo_banner_visible(cfg, feats, "/menu") is False


def test_page_id_for_path():
    assert page_id_for_request_path("/") == "home"
    assert page_id_for_request_path("/menu/burgers") == "menu"
    assert promo_shown_on_path(["deals"], "/deals") is True


def test_popup_desktop_layout_defaults():
    cfg = normalize_promo_banner({})
    assert cfg["popup_subscribe_gap_px"] == 0
    assert cfg["popup_modal_width_px"] == 360
    assert cfg["popup_field_height_px"] == 44
    assert cfg["popup_email_width_pct"] == 82
    assert cfg["popup_subscribe_join_bg"] is True
    assert cfg["popup_join_width_px"] == 0
    assert cfg["show_deals_link"] is True


def test_show_deals_link_can_disable():
    cfg = normalize_promo_banner({"show_deals_link": False})
    assert cfg["show_deals_link"] is False


def test_subscribe_bar_background():
    cfg = normalize_promo_banner({"subscribe_bar_bg_color": "#112233"})
    assert cfg["subscribe_bar_bg_color"] == "#112233"
    assert cfg["subscribe_bar_transparent"] is False
    t = normalize_promo_banner({"subscribe_bar_transparent": True})
    assert t["subscribe_bar_transparent"] is True
