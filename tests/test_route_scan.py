"""scan_routes: prices the Airline Matrix routes the main scan doesn't cover."""
from datetime import date, datetime, timedelta, timezone

import pytest

from bots import scouter
from core import config, queries
from core.db import utcnow

TODAY = date(2026, 11, 7)
DESTS = [{"iata": "CAK", "carriers": ["MX"]}, {"iata": "ATL", "carriers": ["DL", "F9"]}, {"iata": "XXX", "carriers": []}]


def fare(airline, dest, price, depart, ret=None, stops=0):
    return {"origin": "TPA", "destination": dest, "trip_type": "round_trip" if ret else "one_way", "depart_date": depart,
            "return_date": ret, "stops": stops, "price_usd": price, "airline_iata": airline, "source": "test",
            "flight_numbers": f"{airline}1"}


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(config, "destinations", lambda: DESTS)
    monkeypatch.setattr(scouter, "_sleep", lambda: None)


def run(conn, flights):
    calls = []

    def search(origin, dest, depart, ret=None, nonstop=True):
        calls.append((dest, depart, ret))
        return [fare(a, dest, p, depart, ret, s) for a, p, s, day in flights.get(dest, []) if day in (None, depart)]

    scouter.scan_routes(conn, search, lambda r, party, nonstop: [], TODAY)
    return calls


def stored(conn, trip="one_way"):
    return {(r[0], r[1]): r[2] for r in conn.execute(
        "SELECT airline_iata, destination, price_usd FROM fares WHERE trip_type=? AND scan_mode='airline'", (trip,))}


def test_dates_are_a_tuesday_then_that_friday_with_returns_a_week_later():
    (tue, tue_back), (fri, fri_back) = scouter.route_scan_dates(TODAY)
    assert tue.weekday() == 1 and fri.weekday() == 4 and (fri - tue).days == 3
    assert (tue_back - tue).days == 7 and (fri_back - fri).days == 7


def test_prices_each_listed_route_one_way_and_round_trip(conn, world):
    run(conn, {"CAK": [("MX", 80, 0, None)], "ATL": [("DL", 90, 0, None), ("F9", 40, 0, None)]})
    assert stored(conn) == {("MX", "CAK"): 80, ("DL", "ATL"): 90, ("F9", "ATL"): 40}
    assert stored(conn, "round_trip") == {("MX", "CAK"): 80, ("DL", "ATL"): 90, ("F9", "ATL"): 40}


def test_tries_friday_only_for_airlines_not_found_on_tuesday(conn, world):
    friday = scouter.route_scan_dates(TODAY)[1][0].isoformat()
    calls = run(conn, {"CAK": [("MX", 80, 0, friday)], "ATL": [("DL", 90, 0, None), ("F9", 40, 0, None)]})
    assert [c for c in calls if c[0] == "CAK" and c[2] is None][1][1] == friday and stored(conn)[("MX", "CAK")] == 80
    assert len([c for c in calls if c[0] == "ATL" and c[2] is None]) == 1


def test_skips_recently_priced_routes_and_never_stores_their_fares(conn, world):
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date, stops,
                    price_usd, airline_iata, source) VALUES ('s',?,'ATL','one_way','w','nonstop','2026-12-08',0,70,'DL','t')""",
                 (utcnow(),))
    run(conn, {"ATL": [("DL", 999, 0, None), ("F9", 40, 0, None)]})
    assert ("DL", "ATL") not in stored(conn) and stored(conn)[("F9", "ATL")] == 40


def test_ignores_connections_other_airlines_and_failures(conn, world):
    def search(origin, dest, depart, ret=None, nonstop=True):
        if dest == "CAK":
            raise RuntimeError("blocked")
        return [fare("F9", dest, 40, depart, ret, stops=1), fare("ZZ", dest, 10, depart, ret)]

    scouter.scan_routes(conn, search, lambda r, party, nonstop: [], TODAY)
    assert stored(conn) == {} and conn.execute("SELECT COUNT(*) FROM scan_log WHERE error IS NOT NULL").fetchone()[0] > 0


def test_route_fares_stay_out_of_home_and_deals_but_reach_route_prices(conn, world):
    run(conn, {"CAK": [("MX", 80, 0, None)]})
    conn.execute("UPDATE fares SET status='ready_to_publish'")
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date, stops,
                    price_usd, airline_iata, source, status) VALUES ('main',?,'ATL','one_way','w','nonstop','2026-12-08',0,70,'DL','t',
                    'ready_to_publish')""", (utcnow(),))
    assert [f["destination"] for f in queries.route_prices(conn, "MX")] == ["CAK"]
    assert queries.latest_scan(conn)["scan_id"] == "main"
    assert "MX" not in {f["airline_iata"] for f in queries.cheapest_nonstops(conn, "one_way", 5)}


def test_airline_fallback_searches_the_route_dates_and_keeps_the_cheaper(conn, world, monkeypatch):
    monkeypatch.setattr(scouter, "today_local", lambda: TODAY)
    (tue, _), (fri, _) = scouter.route_scan_dates(TODAY)
    prices = {tue.isoformat(): 945, fri.isoformat(): 210}
    calls = []

    def search(origin, dest, depart, ret=None, nonstop=True):
        calls.append(depart)
        return [fare("MX", dest, prices[depart], depart)]

    scouter.scan_airline_routes(conn, "s", utcnow(), seen=set(), search=search)
    assert set(calls) == set(prices)
    conn.execute("UPDATE fares SET status='ready_to_publish'")
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date, stops,
                    price_usd, airline_iata, source, status) VALUES ('main',?,'ATL','one_way','w','nonstop','2026-12-08',0,70,'DL','t',
                    'ready_to_publish')""", (utcnow(),))
    assert queries.airline_deals(conn, "MX")["cheapest_nonstop"]["price_usd"] == 210


def test_route_scan_due_about_daily(conn, world):
    now = datetime.now(timezone.utc)
    assert scouter.route_scan_due(conn, now=now)
    run(conn, {})
    assert not scouter.route_scan_due(conn, now=now + timedelta(hours=1))
    assert scouter.route_scan_due(conn, now=now + timedelta(hours=21))


def test_one_way_tries_the_rest_of_the_week_for_airlines_still_missing(conn, world):
    week = scouter.route_scan_dates(TODAY, extra=True)
    assert [d.weekday() for d, _ in week] == [1, 4, 2, 3, 5, 6, 0] and all((r - d).days == 7 for d, r in week)
    sat = week[4][0].isoformat()
    calls = run(conn, {"CAK": [("MX", 80, 0, sat)], "ATL": [("DL", 90, 0, None), ("F9", 40, 0, None)]})
    assert [c[1] for c in calls if c[0] == "CAK" and c[2] is None] == [d.isoformat() for d, _ in week[:5]]
    assert stored(conn)[("MX", "CAK")] == 80
    assert len([c for c in calls if c[0] == "ATL"]) == 2  # found on Tuesday both ways: no extra days


def test_extra_days_try_the_airlines_usual_weekday_first(conn, world):
    week = scouter.route_scan_dates(TODAY, extra=True)
    sun = week[5][0]
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date, stops,
                    price_usd, airline_iata, source) VALUES ('old','2026-10-01T00:00:00+00:00','CAK','one_way','routes',
                    'airline','2026-10-18',0,70,'MX','t')""")  # Oct 18, 2026 was a Sunday
    calls = run(conn, {"CAK": [("MX", 80, 0, sun.isoformat())]})
    assert [c[1] for c in calls if c[0] == "CAK" and c[2] is None][2] == sun.isoformat()


def test_coming_soon_airlines_and_the_extra_cap_limit_extra_days(conn, world, monkeypatch):
    soon = [{"iata": "CAK", "carriers": ["MX"], "carrier_status": {"MX": {"status": "coming_soon"}}},
            {"iata": "BGR", "carriers": ["MX"]}, {"iata": "BTV", "carriers": ["MX"]}]
    monkeypatch.setattr(config, "destinations", lambda: soon)
    monkeypatch.setattr(scouter, "ROUTE_EXTRA_SEARCHES", 6)
    calls = [c for c in run(conn, {}) if c[2] is None]
    assert len([c for c in calls if c[0] == "CAK"]) == 2   # Tuesday and Friday only
    assert len([c for c in calls if c[0] == "BGR"]) == 7   # the whole week
    assert len([c for c in calls if c[0] == "BTV"]) == 3   # cap reached after one extra day


def test_round_trip_starts_on_the_day_the_one_way_found_the_airline(conn, world):
    week = scouter.route_scan_dates(TODAY, extra=True)
    sun, sun_back = week[5]
    calls = run(conn, {"CAK": [("MX", 80, 0, sun.isoformat())]})
    assert [c for c in calls if c[0] == "CAK" and c[2]][0] == ("CAK", sun.isoformat(), sun_back.isoformat())
    assert stored(conn, "round_trip")[("MX", "CAK")] == 80


def test_round_trip_tries_shorter_trips_when_the_week_apart_return_has_no_nonstop(conn, world):
    (_, _), (fri, fri_back) = scouter.route_scan_dates(TODAY)
    sun_back = (fri + timedelta(days=2)).isoformat()

    def search(origin, dest, depart, ret=None, nonstop=True):
        calls.append((dest, depart, ret))
        if dest != "CAK" or depart != fri.isoformat() or ret not in (None, sun_back):
            return []
        return [fare("MX", dest, 80, depart, ret)]

    calls = []
    scouter.scan_routes(conn, search, lambda r, party, nonstop: [], TODAY)
    rt = [c for c in calls if c[0] == "CAK" and c[2]]
    assert rt[0] == ("CAK", fri.isoformat(), fri_back.isoformat()) and rt[-1] == ("CAK", fri.isoformat(), sun_back)
    assert stored(conn, "round_trip")[("MX", "CAK")] == 80
