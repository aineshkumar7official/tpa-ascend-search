from core import queries

AT = "2026-11-03T20:00:00+00:00"


def test_older_cheaper_scan_never_overrides_the_newest_price(conn):
    _fare(conn, trip="one_way", price=19, scan="old", at="2026-11-03T02:00:00+00:00")   # same calendar day as the cutoff
    _fare(conn, trip="one_way", price=84, scan="new", at="2026-11-04T16:00:00+00:00")
    assert [f["price_usd"] for f in queries.route_prices(conn, "DL")] == [84]
    assert queries.airline_deals(conn, "DL", "one_way")["cheapest"]["price_usd"] == 84


def test_route_missed_by_last_scan_keeps_its_recent_price_until_it_ages_out(conn):
    _fare(conn, trip="one_way", price=90, dest="BOS", scan="new", at="2026-11-04T16:00:00+00:00")
    _fare(conn, trip="one_way", price=50, dest="ATL", scan="prev", at="2026-11-04T04:00:00+00:00")
    _fare(conn, trip="one_way", price=10, dest="LAX", scan="stale", at="2026-11-03T02:00:00+00:00")
    assert {f["destination"]: f["price_usd"] for f in queries.route_prices(conn, "DL")} == {"ATL": 50, "BOS": 90}


def _fare(conn, airline="DL", trip="round_trip", stops=0, price=100, mins=120, mode="nonstop", dest="ATL", scan="s1", at=AT):
    conn.execute(
        """INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, depart_date, stops, price_usd,
                             duration_min, airline_iata, source, status, scan_mode)
           VALUES (?,?,?,?,'mid+4','2026-12-01',?,?,?,?,'test','ready_to_publish',?)""",
        (scan, at, dest, trip, stops, price, mins, airline, mode))
    conn.commit()


def test_no_fares_leaves_every_slot_empty(conn):
    assert queries.airline_deals(conn, "DL") == {"cheapest": None, "fastest_nonstop": None, "cheapest_nonstop": None}


def test_fastest_and_cheapest_nonstop_can_differ(conn):
    _fare(conn, price=100, mins=200)
    _fare(conn, price=150, mins=90)
    d = queries.airline_deals(conn, "DL", "round_trip")
    assert d["cheapest_nonstop"]["price_usd"] == 100
    assert d["fastest_nonstop"]["price_usd"] == 150
    assert d["cheapest"]["price_usd"] == 100


def test_cheapest_includes_stops_only_when_cheaper(conn):
    _fare(conn, trip="one_way", price=100)
    _fare(conn, trip="one_way", stops=1, price=80, mins=400, mode="any", scan="s2")
    d = queries.airline_deals(conn, "DL", "one_way")
    assert d["cheapest"]["price_usd"] == 80 and d["cheapest"]["stops"] == 1
    assert d["cheapest_nonstop"]["price_usd"] == 100 and d["fastest_nonstop"]["price_usd"] == 100


def test_trip_type_and_airline_are_kept_apart(conn):
    _fare(conn, trip="one_way", price=50)
    _fare(conn, airline="UA", price=60)
    assert queries.airline_deals(conn, "DL", "round_trip")["cheapest"] is None
    assert queries.airline_deals(conn, "DL", "one_way")["cheapest"]["price_usd"] == 50


def test_route_prices_keep_cheapest_per_destination(conn):
    _fare(conn, trip="one_way", price=120, dest="ATL")
    _fare(conn, trip="one_way", price=90, dest="ATL")
    _fare(conn, trip="one_way", price=70, dest="BOS")
    assert [(f["destination"], f["price_usd"]) for f in queries.route_prices(conn, "DL")] == [("BOS", 70), ("ATL", 90)]
