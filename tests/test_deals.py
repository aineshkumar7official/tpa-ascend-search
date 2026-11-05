from datetime import datetime, timedelta, timezone

from bots.scouter import detect_deals


def _seed(conn, prices, dest="JFK"):
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=len(prices) // 4 + 1)
    scan_id = None
    for i, p in enumerate(prices):
        at = (start + timedelta(hours=6 * i)).isoformat()
        scan_id = f"s{i}"
        conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,1)", (dest, "one_way", "mid+4", at, p))
        conn.execute(
            """INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, depart_date,
                                 stops, price_usd, source) VALUES (?,?,?,?,?,?,0,?,'test')""",
            (scan_id, at, dest, "one_way", "mid+4", "2026-11-24", p),
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
