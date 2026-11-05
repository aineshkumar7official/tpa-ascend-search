"""Bot 1 — Scouter: scans TPA nonstops into `fares` + `price_history`, then flags deals."""
import json
import logging
import random
import statistics
import time
import uuid
from datetime import datetime, timedelta

from core import config
from core.config import settings
from core.dates import today_local, windows as date_windows
from core.db import utcnow
from sources import flights_fast

log = logging.getLogger(__name__)

TRIP_TYPES = ("one_way", "round_trip")
ANY_STOPS_WINDOW = "mid+4"   # Airline Matrix "absolute cheapest" scan runs on one window only
FALLBACK_DAYS = 14           # Airline Matrix: nonstops this far out for airlines the main scan missed
FALLBACK_WINDOW = f"d+{FALLBACK_DAYS}"
DROP_THRESHOLD = 0.20
BASELINE_DAYS = 14
MIN_POINTS = 6
PRUNE_AFTER = 3              # consecutive scans with zero nonstops before we flag a route

FARE_COLUMNS = (
    "scan_id", "scanned_at", "origin", "destination", "trip_type", "window_id", "scan_mode",
    "depart_date", "return_date", "stops", "price_usd", "airline_iata", "airline_name",
    "flight_numbers", "aircraft_type", "depart_time", "arrive_time", "duration_min",
    "via_airports", "segments", "search_url", "source",
)


def _sleep():
    time.sleep(random.uniform(*settings.SCAN_DELAY))


def insert_fares(conn, rows, scan_id, scanned_at, window_id, scan_mode):
    for r in rows:
        segs = r.get("segments")
        vals = {**r, "segments": json.dumps(segs) if segs else None, "scan_id": scan_id, "scanned_at": scanned_at, "window_id": window_id, "scan_mode": scan_mode}
        conn.execute(
            f"INSERT INTO fares ({','.join(FARE_COLUMNS)}) VALUES ({','.join('?' * len(FARE_COLUMNS))})",
            [vals.get(c) for c in FARE_COLUMNS],
        )


def _log_search(conn, scan_id, scanned_at, dest, window_id, trip_type, scan_mode, count, error=None):
    conn.execute(
        "INSERT INTO scan_log VALUES (?,?,?,?,?,?,?,?)",
        (scan_id, scanned_at, dest, window_id, trip_type, scan_mode, count, error),
    )


def scan(conn, destinations=None, limit=None, dry_run=False, with_any_stops=True, search=None):
    """Run one scan cycle. Returns the scan_id (or the list of rows when dry_run)."""
    search = search or flights_fast.search
    dests = destinations or [d["iata"] for d in config.scan_destinations()]
    if limit:
        dests = dests[:limit]
    scan_id = str(uuid.uuid4())
    scanned_at = utcnow()
    collected = []
    jobs = [(d, w, t, "nonstop") for d in dests for w in date_windows() for t in TRIP_TYPES]
    if with_any_stops:
        jobs += [(d, w, "one_way", "any") for d in dests for w in date_windows() if w["window_id"] == ANY_STOPS_WINDOW]

    for i, (dest, w, trip_type, mode) in enumerate(jobs):
        ret = w["return"] if trip_type == "round_trip" else None
        try:
            results = search(settings.ORIGIN, dest, w["depart"], ret, nonstop=(mode == "nonstop"))
        except Exception as e:  # never fall back to SerpApi here — protect the quota
            log.warning("scan %s %s %s failed: %s", dest, w["window_id"], trip_type, e)
            if not dry_run:
                _log_search(conn, scan_id, scanned_at, dest, w["window_id"], trip_type, mode, 0, str(e))
                conn.commit()
            results = None
        if results is not None:
            rows = [r for r in results if r["stops"] == 0] if mode == "nonstop" else results
            if dry_run:
                for r in rows:
                    print(f"{mode:7} {w['window_id']:8} {trip_type:10} TPA-{dest} {r['airline_iata'] or '?':3} "
                          f"{r['flight_numbers'] or '':14} ${r['price_usd']:.0f} stops={r['stops']} {r['aircraft_type'] or ''}")
                collected.extend(rows)
            else:
                insert_fares(conn, rows, scan_id, scanned_at, w["window_id"], mode)
                nonstop = [r["price_usd"] for r in rows if r["stops"] == 0]
                if mode == "nonstop" and nonstop:
                    conn.execute(
                        "INSERT OR REPLACE INTO price_history VALUES (?,?,?,?,?,1)",
                        (dest, trip_type, w["window_id"], scanned_at, min(nonstop)),
                    )
                _log_search(conn, scan_id, scanned_at, dest, w["window_id"], trip_type, mode, len(rows))
                conn.commit()
        if i < len(jobs) - 1:
            _sleep()

    if with_any_stops and not limit:
        seen = {r["airline_iata"] for r in collected} if dry_run else {r[0] for r in conn.execute(
            "SELECT DISTINCT airline_iata FROM fares WHERE scan_id=?", (scan_id,))}
        collected.extend(scan_airline_routes(conn, scan_id, scanned_at, seen, dry_run, search) or [])

    if dry_run:
        return collected
    flag_dead_routes(conn)
    detect_deals(conn, scan_id)
    return scan_id


def scan_airline_routes(conn, scan_id, scanned_at, seen, dry_run=False, search=None):
    """For TPA carriers (destinations.json) with no fares in this scan, search one of their
    routes per airline for nonstops FALLBACK_DAYS out, so every airline gets a Matrix photo/deal.

    Rows are stored with scan_mode='airline' so they stay out of Home/Deals and price history.
    """
    search = search or flights_fast.search
    routes = {}
    for d in config.destinations():
        for c in d.get("carriers", []):
            if (d.get("carrier_status", {}).get(c) or {}).get("status", "current") == "current":
                routes.setdefault(c, []).append(d["iata"])
    want = {c for c in routes if c not in seen}
    dests = sorted({routes[c][0] for c in want})
    depart = (today_local() + timedelta(days=FALLBACK_DAYS)).isoformat()
    collected = []
    for dest in dests:
        _sleep()
        try:
            results = search(settings.ORIGIN, dest, depart, None, nonstop=True)
        except Exception as e:
            log.warning("airline fallback %s failed: %s", dest, e)
            if not dry_run:
                _log_search(conn, scan_id, scanned_at, dest, FALLBACK_WINDOW, "one_way", "airline", 0, str(e))
                conn.commit()
            continue
        rows = [r for r in results if r["stops"] == 0 and r["airline_iata"] in want]
        if dry_run:
            collected.extend(rows)
            continue
        insert_fares(conn, rows, scan_id, scanned_at, FALLBACK_WINDOW, "airline")
        _log_search(conn, scan_id, scanned_at, dest, FALLBACK_WINDOW, "one_way", "airline", len(rows))
        conn.commit()
    log.info("airline fallback: %d airlines, %d routes searched for %s", len(want), len(dests), depart)
    return collected


def flag_dead_routes(conn):
    """Log (don't delete) destinations with zero nonstops for PRUNE_AFTER scans in a row."""
    dead = []
    for (dest,) in conn.execute("SELECT DISTINCT destination FROM scan_log WHERE scan_mode='nonstop'").fetchall():
        scans = conn.execute(
            """SELECT scan_id, SUM(result_count) AS n, SUM(error IS NOT NULL) AS errs
               FROM scan_log WHERE destination=? AND scan_mode='nonstop'
               GROUP BY scan_id ORDER BY MAX(scanned_at) DESC LIMIT ?""",
            (dest, PRUNE_AFTER),
        ).fetchall()
        if len(scans) == PRUNE_AFTER and all(s["n"] == 0 and s["errs"] == 0 for s in scans):
            dead.append(dest)
    for d in dead:
        log.warning("No nonstop results for TPA-%s in the last %d scans; consider removing it from destinations.json",
                    d, PRUNE_AFTER)
    return dead


def detect_deals(conn, scan_id):
    """Insert deal_alerts for this scan. Returns the number of alerts created."""
    row = conn.execute("SELECT scanned_at FROM fares WHERE scan_id=? LIMIT 1", (scan_id,)).fetchone()
    if not row:
        return 0
    scanned_at = row["scanned_at"]
    since = (datetime.fromisoformat(scanned_at) - timedelta(days=BASELINE_DAYS)).isoformat()
    targets = {r["destination"]: r["target_usd"] for r in conn.execute("SELECT * FROM watchlist")}
    created = 0
    current = conn.execute(
        "SELECT * FROM price_history WHERE scanned_at=? AND nonstop_only=1", (scanned_at,)
    ).fetchall()
    for ph in current:
        key = (ph["destination"], ph["trip_type"], ph["window_id"])
        prev = [r[0] for r in conn.execute(
            """SELECT min_price FROM price_history
               WHERE destination=? AND trip_type=? AND window_id=? AND nonstop_only=1 AND scanned_at<?""",
            (*key, scanned_at),
        )]
        recent = [r[0] for r in conn.execute(
            """SELECT min_price FROM price_history
               WHERE destination=? AND trip_type=? AND window_id=? AND nonstop_only=1
                 AND scanned_at>=? AND scanned_at<?""",
            (*key, since, scanned_at),
        )]
        fare = conn.execute(
            """SELECT id FROM fares WHERE scan_id=? AND destination=? AND trip_type=? AND window_id=?
               AND scan_mode='nonstop' AND stops=0 ORDER BY price_usd LIMIT 1""",
            (scan_id, *key),
        ).fetchone()
        if not fare:
            continue
        cur = ph["min_price"]
        reasons = []
        drop = None
        if len(recent) >= MIN_POINTS:
            baseline = statistics.median(recent)
            drop = (baseline - cur) / baseline if baseline else None
            if drop is not None and drop >= DROP_THRESHOLD:
                reasons.append("drop_20pct")
        if len(prev) >= MIN_POINTS and cur < min(prev):
            reasons.append("new_low")
        target = targets.get(ph["destination"])
        if target is not None and cur <= target:
            reasons.append("under_target")
        for reason in reasons:
            # One unread alert per route/window/reason is enough; don't repeat it every scan.
            dup = conn.execute(
                """SELECT 1 FROM deal_alerts a JOIN fares f ON f.id=a.fare_id
                   WHERE a.seen=0 AND a.reason=? AND f.destination=? AND f.trip_type=? AND f.window_id=?""",
                (reason, *key),
            ).fetchone()
            if dup:
                continue
            conn.execute(
                "INSERT INTO deal_alerts(created_at, fare_id, reason, drop_pct) VALUES (?,?,?,?)",
                (utcnow(), fare["id"], reason, drop),
            )
            created += 1
    conn.commit()
    return created
