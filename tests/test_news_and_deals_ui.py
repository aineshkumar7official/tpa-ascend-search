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


def _seed(conn, n_hist, dest="ATL"):
    now = datetime(2026, 11, 2, 12)
    for i in range(n_hist):
        t = (now - timedelta(hours=6 * (i + 1))).isoformat()
        conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1)", (dest, "one_way", "wkend+2", t, 100.0))
    conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1)", (dest, "one_way", "wkend+2", now.isoformat(), 70.0))
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
