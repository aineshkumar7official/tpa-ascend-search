from datetime import date

import pytest

from bots import enricher
from core import queries
from core.ui import CMP_ROWS, NO_AMENITIES, amenity_chips, entertainment_html, fee_table_cell, has_no_amenities, policy_is_stale, reviews_line


def test_chips_only_for_true():
    html = amenity_chips({"wifi": True, "seatback_screen": False})
    assert "Wi-Fi" in html and "Seatback" not in html and "Stream" not in html
    assert amenity_chips({}) == "" and amenity_chips(None) == ""


def test_verified_none_differs_from_unknown():
    none = dict.fromkeys(("wifi", "seatback_screen", "stream_to_device", "power"), False)
    assert has_no_amenities(none) and NO_AMENITIES in entertainment_html(none)
    for partial in ({}, None, {**none, "power": None}):  # anything unconfirmed stays "not verified"
        assert not has_no_amenities(partial) and "Not verified" in entertainment_html(partial)
    assert "Wi-Fi" in entertainment_html({**none, "wifi": True}) and NO_AMENITIES not in entertainment_html({**none, "wifi": True})


def test_fee_table_only_when_rows_given():
    assert fee_table_cell(None) is None and fee_table_cell({"text": "Free"}) is None
    html = fee_table_cell({"label": "Basic fare", "rows": [["Cancel", "$149"]], "note": "Credit only"})
    assert "Basic fare" in html and "Cancel" in html and "$149" in html and "Credit only" in html


def test_compare_table_has_no_reviews_row():
    assert [k for k, _ in CMP_ROWS] == ["aircraft", "legroom", "ent", "food", "bags"]


def test_amenities_fallback_label(monkeypatch):
    table = {"DL|Airbus A321": {"wifi": True}, "DL|*": {"wifi": True, "cool_thing": "x"}}
    monkeypatch.setattr(enricher.config, "amenities", lambda: table)
    assert enricher.amenities_for("DL", "Airbus A321neo") == (table["DL|Airbus A321"], False)
    assert enricher.amenities_for("DL", "Boeing 757-200") == (table["DL|*"], True)
    assert enricher.amenities_for("ZZ", "Boeing 757-200") == ({}, False)


def test_airline_wide_cabin_images_fill_empty_slots(monkeypatch):
    slot = lambda url: {"image_url": url, "credit": None, "source_page": None}
    table = {"F9|Airbus A321neo": {"cabin": slot("exact.jpg"), "food": slot(None)},
             "F9|*": {"cabin": slot("wide.jpg"), "food": slot("wide-food.jpg")}}
    monkeypatch.setattr(enricher.config, "cabins", lambda: table)
    monkeypatch.setattr(enricher.config, "fleet", lambda: {})
    monkeypatch.setattr(enricher.commons, "search", lambda *a, **k: None)
    exact = enricher.fetch_asset(None, "F9", "Airbus A321neo")
    assert exact["interior_url"] == "exact.jpg" and exact["food_url"] == "wide-food.jpg"
    other = enricher.fetch_asset(None, "F9", "Airbus A320neo")  # no entry for this type
    assert other["interior_url"] == "wide.jpg" and other["seat_url"] is None


def test_typical_aircraft_from_fleet(monkeypatch):
    monkeypatch.setattr(enricher.config, "fleet", lambda: {"DL": {"default_type": "Boeing 737-900ER"}})
    assert enricher.resolve_type("DL", None) == ("Boeing 737-900ER", True)
    assert enricher.resolve_type("DL", "Airbus A321") == ("Airbus A321", False)


def test_window_pills():
    assert queries.window_for_pill("Weekend") == "wkend+2"
    assert queries.window_for_pill("Midweek") == "mid+4"
    assert queries.window_for_pill("Long weekend") == "wkend+6"
    assert queries.window_for_pill("Custom") is None
    with pytest.raises(KeyError):
        queries.window_for_pill("Someday")


def test_policy_freshness():
    assert policy_is_stale({"checked": None})
    assert policy_is_stale({"checked": "2026-09-01"}, today=date(2026, 11, 2))
    assert not policy_is_stale({"checked": "2026-10-20"}, today=date(2026, 11, 2))


def test_no_reviews_label():
    assert "No reviews yet" in reviews_line(None)
    assert "No reviews yet" in reviews_line({"match_level": "none", "review_count": 0})


def test_route_vs_airline_labels():
    f = {"airline_iata": "DL", "destination": "JFK"}
    r = {"match_level": "route", "review_count": 12, "stars_5": 3.5}
    assert "Reviews for TPA ⇄ JFK on Delta Air Lines (12)" in reviews_line(r, f)
    r = {"match_level": "airline", "review_count": 340, "stars_5": 3.0}
    assert "General Delta Air Lines economy reviews (340)" in reviews_line(r, f)


def test_sort_price_and_time_stable():
    fares = [{"id": 1, "p": 100, "t": "09:00"}, {"id": 2, "p": 90, "t": "07:00"}, {"id": 3, "p": 100, "t": "06:00"}]
    assert [f["id"] for f in sorted(fares, key=lambda f: f["p"])] == [2, 1, 3]
    assert [f["id"] for f in sorted(fares, key=lambda f: f["t"])] == [3, 2, 1]


def test_clamp_trip_dates():
    from core.ui import clamp_trip_dates
    today = date(2026, 11, 2)
    assert clamp_trip_dates({"depart_date": "2026-11-16", "return_date": "2026-11-19"}, today) == (date(2026, 11, 16), date(2026, 11, 19))
    # saved search from the past -> depart clamps to today, return stays after it
    assert clamp_trip_dates({"depart_date": "2026-10-01", "return_date": "2026-10-04"}, today) == (today, date(2026, 11, 5))
    assert clamp_trip_dates({"depart_date": "2026-12-13", "return_date": None}, today) == (date(2026, 12, 13), date(2026, 12, 16))
