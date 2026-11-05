from core import config, ui


def test_metro_groups_only_searchable_airports():
    assert config.metro_airports("ALL_NYC") == ["JFK", "LGA", "EWR"]
    assert "TKI" not in config.metro_airports("ALL_DFW")          # coming soon -> not searched
    assert config.metro_airports("ATL") == ["ATL"]
    assert config.city("ALL_NYC") == "New York" and config.metro_for("LGA") == "ALL_NYC"


def test_ticked_airports_become_a_destination_code():
    assert config.selection_code([]) is None
    assert config.selection_code(["ORD"]) == "ORD"
    assert config.selection_code(["MDW", "ORD"]) == "ALL_CHI"             # all ticked -> the whole metro
    assert config.selection_code(["EWR", "JFK"]) == "ALL_NYC:JFK,EWR"     # metro order, not tick order


def test_metro_subset_behaves_like_a_metro():
    code = "ALL_NYC:JFK,EWR"
    assert config.is_metro(code) and config.is_metro_subset(code) and not config.is_metro_subset("ALL_NYC")
    assert config.metro_airports(code) == ["JFK", "EWR"]
    assert config.city(code) == "New York"
    assert ui.dest_label(code) == "New York · JFK, EWR"
    assert ui.dest_label("ALL_WAS") == "Washington · all airports"
    assert "JFK, EWR" in ui.dest_header(code) and "All airports" not in ui.dest_header(code)
    assert "All airports" in ui.dest_header("ALL_NYC")


def test_picker_lists_every_city_once_a_to_z():
    rows = ui.dest_rows()
    codes = [r[0] for r in rows]
    metro_airports = {a for m in config.METROS for a in config.metro_airports(m)}
    assert len(codes) == len(set(codes))
    assert set(config.METROS) <= set(codes)
    assert not metro_airports & set(codes)                                # grouped airports only appear under their city
    assert set(codes) | metro_airports >= {d["iata"] for d in config.destinations() if d.get("status") != "coming_soon"}
    names = [ui._sort_key(r[1]) for r in rows]
    assert names == sorted(names)


def test_picker_search_matches_city_or_code():
    assert [r[0] for r in ui.dest_rows("atl")][:1] == ["ATL"]
    assert "ALL_NYC" in [r[0] for r in ui.dest_rows("ewr")]               # an airport finds its city group
    assert "ALL_CHI" in [r[0] for r in ui.dest_rows("chicago")]
    assert ui.dest_rows("zzzz") == []


def test_airport_short_names():
    assert ui.airport_short("ORD") == "ORD · O'Hare"
    assert ui.airport_short("EWR") == "EWR · Newark"
    assert ui.airport_short("JFK") == "JFK"                               # 'New York–JFK' adds nothing to the code
