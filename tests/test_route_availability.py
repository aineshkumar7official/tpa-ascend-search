"""Routes that aren't flying year-round say so (airline 'Routes from TPA' rows and Ascend Search)."""
from core import config, queries, ui

DESTS = [
    {"iata": "CUN", "city": "Cancun", "status": "current", "carriers": ["B6", "MX"],
     "carrier_status": {"B6": {"status": "current"}, "MX": {"status": "coming_soon", "note": "Dec 19, 2026"}}},
    {"iata": "YYC", "city": "Calgary", "status": "seasonal", "carriers": ["WS"], "carrier_status": {"WS": {"status": "seasonal"}}},
    {"iata": "ZRH", "city": "Zurich", "carriers": ["WK"],
     "carrier_status": {"WK": {"status": "suspending", "note": "Suspended from January 2027"}}},
]


def _patch(monkeypatch):
    monkeypatch.setattr(config, "destinations", lambda: DESTS)
    monkeypatch.setattr(config, "destination", lambda i: next((d for d in DESTS if d["iata"] == i), None))
    monkeypatch.setattr(config, "airline_name", lambda c: {"MX": "Breeze Airways", "WS": "WestJet"}.get(c, c))
    monkeypatch.setattr(config, "city", lambda i: (config.destination(i) or {}).get("city", i))


def test_route_availability_explains_routes_not_flying_year_round(monkeypatch):
    _patch(monkeypatch)
    assert ui.route_availability("CUN", "MX") == \
        "Breeze Airways nonstops on TPA → Cancun start Dec 19, 2026; there are no flights before then."
    assert ui.route_availability("CUN", "B6") is None and ui.route_availability("CUN") is None
    assert ui.route_availability("YYC", "WS").startswith("TPA → Calgary is seasonal: WestJet nonstops run only part")
    assert ui.route_availability("YYC").startswith("TPA → Calgary is seasonal: nonstops run")
    assert "Suspended from January 2027" in ui.route_availability("ZRH", "WK")


def test_unpriced_text_says_why_a_route_has_no_price():
    assert ui.unpriced_text("coming_soon", None) == "Not flying yet"
    assert ui.unpriced_text("seasonal", "2026-11-01T12:00:00+00:00") == "Not flying now"
    assert ui.unpriced_text("current", "2026-11-07T22:55:59+00:00") == "No flights since Nov 7"
    assert ui.unpriced_text("current", None) == "No flights found"


def test_last_nonstop_seen_is_the_newest_nonstop_per_route(conn):
    for at, dest, stops in [("2026-11-05T10:00:00+00:00", "LHR", 0), ("2026-11-07T22:55:59+00:00", "LHR", 0),
                            ("2026-11-12T10:00:00+00:00", "LHR", 1), ("2026-11-06T10:00:00+00:00", "LGW", 0)]:
        conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date,
                        stops, price_usd, airline_iata, source) VALUES ('s',?,?,'one_way','w','airline','2026-12-01',?,500,'BA','t')""",
                     (at, dest, stops))
    assert queries.last_nonstop_seen(conn, "BA") == {"LHR": "2026-11-07T22:55:59+00:00", "LGW": "2026-11-06T10:00:00+00:00"}
    assert queries.last_nonstop_seen(conn, "VS") == {}


def test_route_checks_override_airline_status_and_recompute_the_destination():
    dests = [{"iata": "GRR", "status": "current", "seasonal": True, "carriers": ["F9", "WN"],
              "carrier_status": {"F9": {"status": "current"}, "WN": {"status": "current"}}},
             {"iata": "ROC", "status": "current", "carriers": ["MX", "WN"],
              "carrier_status": {"MX": {"status": "current"}, "WN": {"status": "current"}}},
             {"iata": "TYS", "status": "current", "carriers": ["WN"], "carrier_status": {"WN": {"status": "current"}}}]
    checks = {"F9|GRR": {"status": "not_flying", "note": "No flights through Feb 2027"},
              "WN|GRR": {"status": "not_flying", "note": "No flights through Feb 2027"},
              "WN|ROC": {"status": "seasonal", "note": "Flights from Jan 2027"},
              "WN|TYS": {"status": "seasonal", "note": "Flights from Feb 2027"}}
    grr, roc, tys = config._apply_route_checks(dests, checks)
    assert grr["status"] == "not_flying" and grr["status_note"] == "No flights through Feb 2027"
    assert roc["status"] == "current" and roc["carrier_status"]["WN"]["status"] == "seasonal"
    assert tys["status"] == "seasonal" and tys["seasonal"] and tys["status_note"] == "Flights from Feb 2027"
    assert dests[0]["carrier_status"]["F9"] == {"status": "current"}  # the loaded file is never changed


def test_every_route_check_names_a_listed_airline_route():
    raw = config.load_json("destinations.json")["destinations"]
    listed = {f"{a}|{d['iata']}" for d in raw for a in d.get("carriers", [])}
    checks = config.load_json("route_checks.json")["routes"]
    assert set(checks) <= listed
    assert all(c["status"] in config.STATUS_RANK for c in checks.values())


def test_not_flying_routes_say_so(monkeypatch):
    _patch(monkeypatch)
    DESTS.append({"iata": "TTN", "city": "Trenton", "status": "not_flying", "carriers": ["F9"],
                  "carrier_status": {"F9": {"status": "not_flying", "note": "No flights through Feb 2027"}}})
    try:
        assert ui.route_availability("TTN", "F9") == "F9 nonstops on TPA → Trenton aren't flying right now (No flights through Feb 2027)."
        assert ui.unpriced_text("not_flying", None) == "Not flying now"
        assert ui.dest_label("TTN").endswith(" · not flying now")
    finally:
        DESTS.pop()
