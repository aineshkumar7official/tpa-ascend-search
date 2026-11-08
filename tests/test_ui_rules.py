from datetime import date

import pytest

from bots import enricher
from core import queries
from core.config import airline_description
from core.ui import (CMP_ROWS, FEE_ROWS, NO_AMENITIES, amenity_chips, entertainment_html, has_no_amenities, policy_is_stale,
                     reviews_line, same_flight, trend_summary)


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


def test_v6_fees_card_rows():
    assert [k for k, _ in FEE_ROWS] == ["personal_item", "carry_on", "first_checked", "seat_selection", "loyalty_program"]


def test_description_template_from_hq_and_alliance(monkeypatch):
    from core import config

    table = {"AA": {"name": "A Air", "hq": "Fort Worth", "alliance": "oneworld", "description": None},
             "BB": {"name": "B Air", "hq": "Denver", "alliance": None},
             "CC": {"name": "C Air", "hq": "Dallas", "description": "Written by hand."},
             "DD": {"name": "D Air"}}
    monkeypatch.setattr(config, "airline", lambda code: table[code])
    assert airline_description("AA") == "A Air is based in Fort Worth and is part of oneworld."
    assert airline_description("BB") == "B Air is based in Denver and is not part of an alliance."
    assert airline_description("CC") == "Written by hand." and airline_description("DD") is None


def test_freebie_and_fun_fact_dont_repeat_each_other():
    from core.ui import freebie_lines

    assert freebie_lines("Free trading cards", "American offers free trading cards.") == ["Free trading cards"]
    assert freebie_lines("Trading cards", "Delta offers trading cards.") == ["Trading cards"]
    assert freebie_lines("Trading cards", "Atlanta is Delta's largest hub.") == ["Trading cards", "Atlanta is Delta's largest hub."]
    assert freebie_lines(None, "A fact.") == ["A fact."] and freebie_lines(None, None) == []


def test_best_deal_only_when_all_three_slots_are_one_flight():
    a = {"flight_numbers": "DL1", "depart_date": "2026-12-01", "return_date": None}
    b = {**a, "flight_numbers": "DL2"}
    assert same_flight({"cheapest": a, "fastest_nonstop": dict(a), "cheapest_nonstop": dict(a)}) == a
    assert same_flight({"cheapest": a, "fastest_nonstop": b, "cheapest_nonstop": a}) is None
    assert same_flight({"cheapest": a, "fastest_nonstop": None, "cheapest_nonstop": a}) is None
    unknown = {"flight_numbers": None, "depart_date": "2026-12-01", "return_date": None}
    assert same_flight({"cheapest": unknown, "fastest_nonstop": unknown, "cheapest_nonstop": unknown}) is None


def test_trend_summary_is_honest_about_span_and_today():
    days = [(date(2026, 1, 1), 200.0), (date(2026, 1, 2), 100.0)]
    html = trend_summary(days)
    assert "2-day average" in html and "$150" in html and "Lowest · Jan 2" in html and "Highest · Jan 1" in html
    assert "Latest · Jan 2" in html and "Today" not in html       # the last price check wasn't today
    assert "▼ 33% vs. 2-day avg" in html


def test_compare_table_rows_follow_v7():
    assert [k for k, _ in CMP_ROWS] == ["aircraft", "bags", "food", "ent", "freebie"]


def test_chip_popups_list_only_that_flights_amenities():
    html = amenity_chips({"wifi": True, "wifi_cost": "Free", "power": False})
    assert "Wi-Fi" in html and "Cost" in html and "Free" in html and "Speed" in html and "Not verified yet" in html
    assert "Outlet type" not in html


def test_amenities_fallback_label(monkeypatch):
    table = {"DL|Airbus A321": {"wifi": True}, "DL|*": {"wifi": True, "cool_thing": "x"}}
    monkeypatch.setattr(enricher.config, "amenities", lambda: table)
    assert enricher.amenities_for("DL", "Airbus A321neo") == (table["DL|Airbus A321"], False)
    assert enricher.amenities_for("DL", "Boeing 757-200") == (table["DL|*"], True)
    assert enricher.amenities_for("ZZ", "Boeing 757-200") == ({}, False)


SAVED = {"destination": "BOS", "depart_date": "2026-12-01", "return_date": "2026-12-04", "mode": "rt_legs", "nonstop": False,
         "party": {"adults": 2, "children": 1, "infants": 0}, "carry_on": 1, "checked": 2}
TODAY = date(2026, 11, 7)


def test_route_row_opens_its_exact_conditions():
    from core.ui import route_search

    one_way = route_search(SAVED, "ATL", False, {"depart_date": "2026-12-08", "return_date": None}, "DL", TODAY)
    assert (one_way["destination"], one_way["airline"], one_way["depart_date"], one_way["return_date"]) == ("ATL", "DL", "2026-12-08", None)
    assert one_way["mode"] == "one_way" and one_way["nonstop"] is True
    assert one_way["party"] == SAVED["party"] and (one_way["carry_on"], one_way["checked"]) == (1, 2)   # what the user already picked

    both = route_search(SAVED, "ATL", True, {"depart_date": "2026-12-08", "return_date": "2026-12-15"}, "DL", TODAY)
    assert (both["depart_date"], both["return_date"], both["mode"]) == ("2026-12-08", "2026-12-15", "rt_legs")
    assert route_search({**SAVED, "mode": "one_way"}, "ATL", True, None, "DL", TODAY)["mode"] == "rt_bundles"


def test_route_row_without_a_usable_fare_uses_saved_dates():
    from core.ui import route_search

    unpriced = route_search(SAVED, "ATL", True, None, "DL", TODAY)
    assert (unpriced["depart_date"], unpriced["return_date"], unpriced["airline"]) == ("2026-12-01", "2026-12-04", "DL")
    gone = route_search(SAVED, "ATL", True, {"depart_date": "2026-11-01", "return_date": "2026-11-03"}, "DL", TODAY)
    assert gone["depart_date"] == "2026-12-01"


def test_results_limit_to_the_rows_airline_only_when_set():
    from core.ui import only_airline

    fares = [{"airline_iata": "DL"}, {"airline_iata": "AA"}]
    assert only_airline(fares, {"airline": "DL"}) == [{"airline_iata": "DL"}]
    assert only_airline(fares, {"airline": None}) == fares and only_airline(fares, {}) == fares


def test_route_only_food_shows_only_on_that_route(monkeypatch):
    table = {"DL|Airbus A330": {"food_drinks": "Snacks"},
             "DL|*": {"food_drinks": "Snacks", "routes": {"AMS": {"food_drinks": "Full meal"}}},
             "AA|*": {"food_drinks": "Other"}}
    monkeypatch.setattr(enricher.config, "amenities", lambda: table)
    food = lambda airline, plane, route=(): enricher.amenities_for(airline, plane, route)[0]["food_drinks"]  # noqa: E731
    assert food("DL", None, ("TPA", "AMS")) == "Full meal"
    assert food("DL", None, ("AMS", "TPA")) == "Full meal"
    assert food("DL", "Airbus A330", ("TPA", "AMS")) == "Full meal"      # an aircraft entry doesn't lose the route rule
    assert food("DL", None, ("TPA", "ATL")) == "Snacks"
    assert food("DL", None) == "Snacks"                                  # airline-wide, no route known
    assert food("AA", None, ("TPA", "AMS")) == "Other"                   # another airline's flight to the same city


def test_delta_food_text_only_mentions_amsterdam_on_amsterdam_flights():
    def food(route):
        return enricher.amenities_for("DL", "Boeing 757", route)[0]["food_drinks"]

    assert "Amsterdam" not in food(("TPA", "ATL")) and "Cheez-It" in food(("TPA", "ATL"))
    assert "buy on board also available" in food(("TPA", "ATL"))
    assert "entree" in food(("TPA", "AMS")) and "entree" in food(("AMS", "TPA"))
    assert "entree" not in food(("TPA", "ATL"))


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


def test_curated_exterior_beats_automatic_photo_searches(monkeypatch):
    slot = {"image_url": "/app/static/plane.jpg", "credit": "Photo: Someone, CC0", "source_page": "https://example.org/plane"}
    monkeypatch.setattr(enricher.config, "cabins", lambda: {"WK|*": {"exterior": slot}})
    monkeypatch.setattr(enricher.config, "fleet", lambda: {"WK": {"representative_tails": {"Airbus A350-900": "HB-IHF"}}})
    monkeypatch.setattr(enricher.planespotters, "by_registration", lambda *a, **k: {"url": "spotter.jpg", "source": "planespotters"})
    monkeypatch.setattr(enricher.commons, "search", lambda *a, **k: None)
    a = enricher.fetch_asset(None, "WK", "Airbus A350-900")
    assert a["exterior_url"] == "/app/static/plane.jpg" and a["exterior_source"] == "curated"
    assert a["exterior_credit"] == "Photo: Someone, CC0" and a["exterior_link"] == "https://example.org/plane"


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


def test_live_search_progress_passes_status_label_by_keyword():
    # StatusContainer.update() only takes keywords, so progress=status.update crashes Custom search.
    from pathlib import Path
    page = (Path(__file__).parent.parent / "views" / "1_Ascend_Deals.py").read_text()
    assert "progress=status.update" not in page


def test_local_images_use_relative_paths_for_streamlit_cloud():
    from core.ui import asset_src, image
    assert asset_src("/app/static/airlines/SY/exterior.jpg") == "app/static/airlines/SY/exterior.jpg"
    assert asset_src("https://upload.wikimedia.org/x.jpg") == "https://upload.wikimedia.org/x.jpg"
    assert asset_src(None) is None
    assert 'src="app/static/a.jpg"' in image("/app/static/a.jpg")
