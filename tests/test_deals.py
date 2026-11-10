from datetime import datetime, timedelta, timezone

from bots.scouter import detect_deals


def _seed(conn, prices, dest="JFK", depart_for=lambda i: "2026-11-24"):
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=len(prices) // 4 + 1)
    scan_id = None
    for i, p in enumerate(prices):
        at = (start + timedelta(hours=6 * i)).isoformat()
        scan_id = f"s{i}"
        conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1,?)",
                     (dest, "one_way", "mid+4", at, p, depart_for(i)))
        conn.execute(
            """INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, depart_date,
                                 stops, price_usd, source) VALUES (?,?,?,?,?,?,0,?,'test')""",
            (scan_id, at, dest, "one_way", "mid+4", depart_for(i), p),
        )
    conn.commit()
    return scan_id


def _alerts(conn):
    return [r["reason"] for r in conn.execute("SELECT reason FROM deal_alerts")]


def test_flat_series_then_25pct_drop(conn):
    scan_id = _seed(conn, [200] * 8 + [150])
    detect_deals(conn, scan_id)
    assert sorted(_alerts(conn)) == ["drop_20pct", "new_low"]
    drop = conn.execute("SELECT drop_pct FROM deal_alerts WHERE reason='drop_20pct'").fetchone()[0]
    assert abs(drop - 0.25) < 1e-9


def test_small_drop_no_alert(conn):
    scan_id = _seed(conn, [200] * 8 + [190, 195])
    detect_deals(conn, scan_id)
    assert _alerts(conn) == []


def test_not_enough_history(conn):
    scan_id = _seed(conn, [200, 200, 100])
    detect_deals(conn, scan_id)
    assert _alerts(conn) == []


def test_under_target_not_repeated(conn):
    conn.execute("INSERT INTO watchlist VALUES ('JFK', 210)")
    scan_id = _seed(conn, [200, 200])
    detect_deals(conn, scan_id)
    detect_deals(conn, scan_id)
    assert _alerts(conn) == ["under_target"]


def test_price_for_another_departure_date_is_not_a_drop(conn):
    # Eight checks for Dec 1 at $200, then the window rolls to Dec 8 at $100: a different date, not a deal.
    scan_id = _seed(conn, [200] * 8 + [100], depart_for=lambda i: "2026-12-01" if i < 8 else "2026-12-08")
    detect_deals(conn, scan_id)
    assert _alerts(conn) == []


def test_drop_still_detected_after_window_rolls(conn):
    scan_id = _seed(conn, [50] * 3 + [200] * 8 + [150], depart_for=lambda i: "2026-12-01" if i < 3 else "2026-12-08")
    detect_deals(conn, scan_id)
    assert sorted(_alerts(conn)) == ["drop_20pct", "new_low"]


def test_scan_records_departure_date(conn):
    from bots.scouter import scan
    from core.dates import windows
    fare = {"stops": 0, "price_usd": 100.0, "airline_iata": "DL", "source": "test", "origin": "TPA"}

    def search(origin, dest, depart, ret, nonstop):
        return [{**fare, "destination": dest, "depart_date": depart, "return_date": ret,
                 "trip_type": "round_trip" if ret else "one_way"}]

    scan(conn, destinations=["ATL"], with_any_stops=False, search=search)
    got = {r["window_id"]: r["depart_date"] for r in conn.execute("SELECT * FROM price_history")}
    assert got == {w["window_id"]: w["depart"] for w in windows()}


def test_migration_backfills_depart_date_from_fares(tmp_path):
    from core.db import connect, init_schema
    conn = connect(str(tmp_path / "old.db"))
    init_schema(conn)
    conn.executescript("""
        ALTER TABLE price_history DROP COLUMN depart_date;
        INSERT INTO price_history VALUES ('JFK','one_way','mid+4','t1',100,1), ('JFK','one_way','mid+4','t0',90,1);
        INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, depart_date, stops, price_usd, source)
          VALUES ('s','t1','JFK','one_way','mid+4','2026-12-08',0,100,'test');""")
    init_schema(conn)
    got = dict(conn.execute("SELECT scanned_at, depart_date FROM price_history").fetchall())
    assert got == {"t1": "2026-12-08", "t0": None}  # t0's fares were pruned: left out of trends
    conn.close()


def _round_trip_scan(conn, return_price, fail=False):
    """One destination; two airlines at $200 and $300, plus a tied second $200 flight."""
    from bots import scouter
    from core.dates import windows

    def fare(airline, number, price, depart, ret):
        return {"origin": "TPA", "destination": "ATL", "stops": 0, "price_usd": price, "airline_iata": airline,
                "airline_name": airline, "flight_numbers": number, "source": "test", "depart_date": depart,
                "return_date": ret, "trip_type": "round_trip" if ret else "one_way", "depart_time": "08:00"}

    looked_up = []

    def search(origin, dest, depart, ret, nonstop):
        return [fare("DL", "DL1", 200.0, depart, ret), fare("DL", "DL2", 200.0, depart, ret),
                fare("B6", "B61", 300.0, depart, ret)]

    def search_returns(outbound, party, nonstop):
        looked_up.append(outbound["flight_numbers"])
        if fail:
            raise RuntimeError("blocked")
        return [{**fare(outbound["airline_iata"], "RET9", return_price + 50, outbound["return_date"], None),
                 "depart_time": "20:00"},
                {**fare(outbound["airline_iata"], "RET1", return_price, outbound["return_date"], None),
                 "depart_time": "17:30", "arrive_time": "19:45", "duration_min": 135,
                 "segments": [{"from": "ATL", "to": "TPA", "date": outbound["return_date"], "flight": "DL9"}]}]

    orig = scouter.settings.SCAN_DELAY
    scouter.settings.SCAN_DELAY = (0, 0)
    try:
        scouter.scan(conn, destinations=["ATL"], with_any_stops=False, search=search, search_returns=search_returns)
    finally:
        scouter.settings.SCAN_DELAY = orig
    assert len(looked_up) == 2 * len(windows())  # cheapest per airline, per window; one-way trips never look up
    return looked_up


def _return_legs(conn):
    import json
    return {r["flight_numbers"]: json.loads(r["return_leg"]) if r["return_leg"] else None
            for r in conn.execute("SELECT * FROM fares WHERE trip_type='round_trip' AND window_id='mid+4'")}


def test_scan_saves_cheapest_return_that_matches_the_price(conn):
    _round_trip_scan(conn, 200.0)
    legs = _return_legs(conn)
    assert legs["DL1"]["flight_numbers"] == "RET1" and legs["DL1"]["depart_time"] == "17:30"
    assert legs["DL2"] is None and legs["B61"] is None  # B6's return is $200 against a $300 fare


def test_scan_keeps_no_return_when_the_price_differs(conn):
    _round_trip_scan(conn, 216.0)
    assert not any(_return_legs(conn).values())


def test_failed_return_lookup_keeps_the_fare_and_is_logged(conn):
    _round_trip_scan(conn, 200.0, fail=True)
    assert set(_return_legs(conn)) == {"DL1", "DL2", "B61"} and not any(_return_legs(conn).values())
    errs = conn.execute("SELECT COUNT(*) FROM scan_log WHERE scan_mode='return' AND error IS NOT NULL").fetchone()[0]
    assert errs == 6


def test_deals_and_booking_use_the_fare_with_the_return_flight(conn):
    from core import booking, queries
    from core.ui import legs_html
    _round_trip_scan(conn, 200.0)
    conn.execute("UPDATE fares SET status='ready_to_publish', scan_mode='nonstop'")
    conn.commit()
    deal = next(d for d in queries.deals(conn, "mid+4", "round_trip") if d["fare"]["airline_iata"] == "DL")
    fare = deal["fare"]
    assert fare["flight_numbers"] == "DL1"  # of the tied $200 fares, the one with its return flight
    html = legs_html(fare)
    assert "5:30" in html and "7:45" in html and "booking page" not in html
    fare["segments"] = [{"from": "TPA", "to": "ATL", "date": fare["depart_date"], "flight": "DL1"}]
    assert "/booking?" in booking.book_url(fare, 1, fare["return_leg"])


def test_round_trip_without_return_flight_points_to_booking_page():
    from core.ui import legs_html
    html = legs_html({"trip_type": "round_trip", "depart_date": "2026-12-01", "return_date": "2026-12-08",
                      "depart_time": "08:00", "arrive_time": "10:00", "duration_min": 120})
    assert "booking page" in html


def test_deals_with_bags_picks_cheapest_total_and_hides_unknown_fees(conn, monkeypatch):
    from core import config, pricing, queries
    pol = {"XX": {"first_checked": {"fee_usd": 10, "each_way": True}},
           "YY": {"first_checked": {"fee_usd": 80, "each_way": True}},
           "ZZ": {"first_checked": {"fee_usd": None}}}
    monkeypatch.setattr(config, "policies", lambda: pol)
    at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for dest, airline, price in (("JFK", "ZZ", 50), ("JFK", "YY", 70), ("JFK", "XX", 100), ("BOS", "ZZ", 60)):
        conn.execute(
            """INSERT INTO fares(scan_id, scanned_at, destination, airline_iata, trip_type, window_id, depart_date,
                                 stops, price_usd, source, scan_mode, status)
               VALUES ('s',?,?,?,'one_way','mid+4','2026-11-24',0,?,'test','nonstop','ready_to_publish')""",
            (at, dest, airline, price))
    conn.commit()
    assert {d["fare"]["destination"]: d["fare"]["airline_iata"] for d in queries.deals(conn, "mid+4", "one_way")} \
        == {"JFK": "ZZ", "BOS": "ZZ"}                                  # no bags: cheapest fare, nothing hidden
    with_bag = queries.deals(conn, "mid+4", "one_way", None, 0, 1, pricing.Party(2))
    assert [(d["fare"]["destination"], d["fare"]["airline_iata"]) for d in with_bag] == [("JFK", "XX")]


def test_standouts_to_show_caps_at_three_and_skips_home_cities():
    from core import queries

    def sd(dest):
        return {"fare": {"destination": dest}}

    pool = [sd("MCO"), sd("JFK"), sd("ATL"), sd("BOS"), sd("DEN"), sd("ORD")]
    shown = queries.standouts_to_show(pool, ["MCO", "LGA"])  # LGA is the same metro as JFK
    assert [d["fare"]["destination"] for d in shown] == ["ATL", "BOS", "DEN"]
    assert len(queries.standouts_to_show(pool, [])) == 3
