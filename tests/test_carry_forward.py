"""A route the newest scan missed keeps its last fare (core.queries.current_fares) on Home, Deals and airline pages."""
from core import queries
from core.ui import carried_note

NEW, PREV, OLD = "2026-11-13T17:44:00+00:00", "2026-11-13T02:38:00+00:00", "2026-11-09T02:00:00+00:00"


def _fare(conn, dest, price, at, scan, depart="2026-11-20", airline="DL", window="mid+4"):
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date,
                    stops, price_usd, airline_iata, source, status) VALUES (?,?,?,'one_way',?,'nonstop',?,0,?,?,
                    'fast_flights','ready_to_publish')""", (scan, at, dest, window, depart, price, airline))
    conn.commit()


def _seed(conn):
    _fare(conn, "ATL", 90, NEW, "new")
    _fare(conn, "ATL", 40, PREV, "prev")               # older and cheaper: the newer ATL price wins
    _fare(conn, "BOS", 60, PREV, "prev", airline="B6")  # missed by the newest scan: kept
    _fare(conn, "LAX", 20, OLD, "old", airline="UA")    # over 3 days old: dropped
    _fare(conn, "MSP", 30, PREV, "prev", depart="2026-11-12", airline="SY")  # flight already gone: dropped


def test_home_keeps_routes_the_newest_scan_missed(conn):
    _seed(conn)
    assert [(f["destination"], f["price_usd"]) for f in queries.cheapest_nonstops(conn)] == [("BOS", 60), ("ATL", 90)]
    assert [f["destination"] for f in queries.cheapest_mix(conn)] == ["BOS", "ATL"]


def test_deals_keep_routes_the_newest_scan_missed(conn):
    _seed(conn)
    got = {d["fare"]["destination"]: d["fare"] for d in queries.deals(conn, "mid+4", "one_way")}
    assert {k: f["price_usd"] for k, f in got.items()} == {"ATL": 90, "BOS": 60}
    assert got["BOS"]["carried_from"] == PREV and "carried_from" not in got["ATL"]
    assert queries.deals(conn, "wkend+2", "one_way") == []  # other windows are untouched


def test_carried_note_names_the_check():
    assert carried_note({"carried_from": PREV}) == "Price from the Nov 12, 9 PM check."
    assert carried_note({}) is None
