from datetime import datetime, timedelta

from core import queries
from sources import news

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Delta adds new nonstop route from Tampa - Tampa Bay Times</title><link>https://a</link>
<source url="x">Tampa Bay Times</source><pubDate>Mon, 20 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Stock market closes higher - Reuters</title><link>https://b</link></item>
<item><title>Delta Air Lines flight attendants vote - AP</title><link>https://c</link><source url="y">AP</source></item>
</channel></rss>"""


def test_news_filter_and_strip_source():
    items = news.parse(RSS, "DL")
    assert [i["url"] for i in items] == ["https://a", "https://c"]  # stock story dropped
    assert items[0]["headline"] == "Delta adds new nonstop route from Tampa"
    assert items[0]["source"] == "Tampa Bay Times" and items[0]["published_at"] == "2026-10-20"


def _seed(conn, n_hist, dest="ATL", hist_depart="2026-11-13"):
    now = datetime(2026, 11, 2, 12)
    for i in range(n_hist):
        t = (now - timedelta(hours=6 * (i + 1))).isoformat()
        conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1,?)",
                     (dest, "one_way", "wkend+2", t, 100.0, hist_depart))
    conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1,'2026-11-13')",
                 (dest, "one_way", "wkend+2", now.isoformat(), 70.0))
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date,
                    stops, price_usd, airline_iata, source, status) VALUES ('s1',?,?, 'one_way','wkend+2','nonstop',
                    '2026-11-13',0,70,'DL','fast_flights','ready_to_publish')""", (now.isoformat(), dest))
    conn.commit()


def test_tracking_state_under_six_points(conn):
    _seed(conn, 3)
    [d] = queries.deals(conn, "wkend+2", "one_way")
    assert d["tracking"] and d["drop_pct"] is None


def test_drop_pct_with_history(conn):
    _seed(conn, 8)
    [d] = queries.deals(conn, "wkend+2", "one_way")
    assert not d["tracking"] and round(d["drop_pct"], 2) == 0.30 and d["baseline"] == 100


def test_other_departure_dates_stay_out_of_the_trend(conn):
    _seed(conn, 8, hist_depart="2026-11-06")
    [d] = queries.deals(conn, "wkend+2", "one_way")
    assert d["tracking"] and d["drop_pct"] is None and d["trend"] == [70.0] and len(d["points"]) == 1


def _deal(price, baseline, tracking=False):
    drop = (baseline - price) / baseline if baseline else None
    return {"fare": {"price_usd": price}, "baseline": baseline, "drop_pct": drop, "tracking": tracking}


def test_standout_rule():
    assert queries.is_standout(_deal(215, 285))                 # 25% and $70 below typical
    assert queries.is_standout(_deal(200, 222.3))               # right at both limits
    assert not queries.is_standout(_deal(191, 204))             # 6%: not enough of a drop
    assert not queries.is_standout(_deal(27, 40))               # 32%, but only $13
    assert not queries.is_standout(_deal(880, 900))             # $20, but only 2%
    assert not queries.is_standout(_deal(240, 119))             # price went up
    assert not queries.is_standout(_deal(70, None, tracking=True))  # no history yet


def _seed_route(conn, dest, window_id, trip_type, depart, history, now_price):
    now = datetime(2026, 11, 2, 12)
    for i, price in enumerate(history):
        t = (now - timedelta(hours=6 * (i + 1))).isoformat()
        conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1,?)", (dest, trip_type, window_id, t, price, depart))
    conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1,?)",
                 (dest, trip_type, window_id, now.isoformat(), now_price, depart))
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date,
                    stops, price_usd, airline_iata, source, status) VALUES ('s1',?,?,?,?,'nonstop',?,0,?,'DL',
                    'fast_flights','ready_to_publish')""", (now.isoformat(), dest, trip_type, window_id, depart, now_price))


def test_standouts_span_windows_within_one_trip_type_biggest_drop_first(conn):
    _seed_route(conn, "ATL", "wkend+2", "one_way", "2026-11-13", [100] * 6, 85)       # -15%, $15: too small
    _seed_route(conn, "JFK", "wkend+6", "round_trip", "2026-12-11", [400] * 6, 340)   # -15%
    _seed_route(conn, "LAX", "wkend+2", "round_trip", "2026-11-13", [500] * 6, 300)   # -40%
    _seed_route(conn, "MSP", "wkend+6", "one_way", "2026-12-11", [300] * 6, 240)      # -20%
    _seed_route(conn, "BOS", "mid+4", "one_way", "2026-12-01", [200] * 6, 120)        # -40%
    _seed_route(conn, "ORD", "mid+4", "round_trip", "2026-12-01", [200] * 6, 260)     # went up
    conn.commit()
    def got(trip_type):
        return [(d["fare"]["destination"], d["window_label"]) for d in queries.standout_deals(conn, trip_type)]

    assert got("one_way") == [("BOS", "Midweek"), ("MSP", "Long weekend")]
    assert got("round_trip") == [("LAX", "Weekend"), ("JFK", "Long weekend")]


def test_a_rolled_date_never_makes_a_standout(conn):
    now = datetime(2026, 11, 2, 12)
    for i in range(6):  # all the history is for the previous departure date
        conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1,?)",
                     ("JFK", "one_way", "mid+4", (now - timedelta(hours=6 * (i + 1))).isoformat(), 400.0, "2026-11-24"))
    _seed_route(conn, "JFK", "mid+4", "one_way", "2026-12-01", [], 100)
    conn.commit()
    assert queries.standout_deals(conn, "one_way") == []
