"""Read-side queries for the web app. Pure functions of a sqlite connection (the UI caches them)."""
import json
import statistics
from datetime import datetime, timedelta

from bots.enricher import amenities_for, curated_photos
from bots.scouter import BASELINE_DAYS, MIN_POINTS
from core import config
from core.dates import WINDOWS
from sources import flights_serpapi

# Deals pill label -> window_id. "Custom" is live-only and never stored.
WINDOW_PILLS = {"Weekend": "wkend+2", "Midweek": "mid+4", "Long weekend": "wkend+6", "Custom": None}
TRIP_PILLS = {"One-way": "one_way", "Round-trip": "round_trip"}


def window_for_pill(label):
    if label not in WINDOW_PILLS:
        raise KeyError(label)
    return WINDOW_PILLS[label]


# ---------------------------------------------------------------- scan meta
def latest_scan(conn, mode="nonstop"):
    row = conn.execute(
        """SELECT scan_id, MAX(scanned_at) AS scanned_at FROM fares
           WHERE scan_mode=? AND status='ready_to_publish'
           GROUP BY scan_id ORDER BY scanned_at DESC LIMIT 1""", (mode,)).fetchone()
    return dict(row) if row else None


def last_scan_time(conn):
    row = conn.execute("SELECT MAX(scanned_at) FROM fares").fetchone()
    return row[0] if row else None


def serpapi_remaining(conn):
    return flights_serpapi.remaining(conn) if flights_serpapi.available() else None


def unseen_alerts(conn):
    return conn.execute("SELECT COUNT(*) FROM deal_alerts WHERE seen=0").fetchone()[0]


def mark_alerts_seen(conn):
    conn.execute("UPDATE deal_alerts SET seen=1 WHERE seen=0")
    conn.commit()


# ---------------------------------------------------------------- hydration
def asset(conn, key):
    if not key:
        return {}
    row = conn.execute("SELECT * FROM assets WHERE asset_key=?", (key,)).fetchone()
    return dict(row) if row else {}


def review_summary(conn, key):
    if not key:
        return None
    row = conn.execute("SELECT * FROM review_summaries WHERE review_key=?", (key,)).fetchone()
    return dict(row) if row else None


def hydrate(conn, fare):
    """Attach asset, review summary and amenities to a fare dict (DB row)."""
    f = dict(fare)
    f["asset"] = asset(conn, f.get("asset_key"))
    f["review"] = review_summary(conn, f.get("review_key"))
    f["amenities"], f["amenities_typical"] = amenities_for(f.get("airline_iata"), f.get("aircraft_type"))
    f.setdefault("travelers", 1)
    return f


def fare_by_id(conn, fare_id):
    """Background fare (integer id) or live result ('L…' id)."""
    fare_id = str(fare_id or "")
    if fare_id.startswith("L"):
        row = conn.execute("SELECT payload_json FROM live_results WHERE fare_id=?", (fare_id,)).fetchone()
        return json.loads(row[0]) if row else None
    if fare_id.isdigit():
        row = conn.execute("SELECT * FROM fares WHERE id=?", (int(fare_id),)).fetchone()
        if row:
            f = hydrate(conn, row)
            f["fare_id"] = str(row["id"])
            return f
    return None


def _ready(conn, sql, args):
    out = []
    for r in conn.execute(sql, args):
        f = hydrate(conn, r)
        f["fare_id"] = str(r["id"])
        out.append(f)
    return out


# ---------------------------------------------------------------- Home
def cheapest_nonstops(conn, trip_type="one_way", n=3):
    """Cheapest nonstop per destination in the latest scan, top n by price."""
    scan = latest_scan(conn)
    if not scan:
        return []
    return _ready(conn, """
        SELECT f.* FROM fares f
        JOIN (SELECT destination, MIN(price_usd) p FROM fares
              WHERE scan_id=? AND trip_type=? AND scan_mode='nonstop' AND stops=0 AND status='ready_to_publish'
              GROUP BY destination) m ON m.destination=f.destination AND m.p=f.price_usd
        WHERE f.scan_id=? AND f.trip_type=? AND f.scan_mode='nonstop' AND f.stops=0 AND f.status='ready_to_publish'
        GROUP BY f.destination ORDER BY f.price_usd, f.depart_date LIMIT ?""",
        (scan["scan_id"], trip_type, scan["scan_id"], trip_type, n))


def nonstop_candidates(conn, trip_type="one_way"):
    """Cheapest nonstop per (destination, airline) in the latest scan — the pool Home re-ranks by the
    with-bags total when 'Bags included' is on (a low fare with high bag fees can lose to another airline)."""
    scan = latest_scan(conn)
    if not scan:
        return []
    return _ready(conn, """
        SELECT f.* FROM fares f
        JOIN (SELECT destination, airline_iata, MIN(price_usd) p FROM fares
              WHERE scan_id=? AND trip_type=? AND scan_mode='nonstop' AND stops=0 AND status='ready_to_publish'
              GROUP BY destination, airline_iata) m
          ON m.destination=f.destination AND m.airline_iata IS f.airline_iata AND m.p=f.price_usd
        WHERE f.scan_id=? AND f.trip_type=? AND f.scan_mode='nonstop' AND f.stops=0 AND f.status='ready_to_publish'
        GROUP BY f.destination, f.airline_iata ORDER BY f.price_usd, f.depart_date""",
        (scan["scan_id"], trip_type, scan["scan_id"], trip_type))


# ---------------------------------------------------------------- Deals
def history(conn, dest, trip_type, window_id, days=BASELINE_DAYS, until=None):
    until = until or datetime.utcnow().isoformat()
    since = (datetime.fromisoformat(until[:19]) - timedelta(days=days)).isoformat()
    return [dict(r) for r in conn.execute(
        """SELECT scanned_at, min_price FROM price_history
           WHERE destination=? AND trip_type=? AND window_id=? AND nonstop_only=1 AND scanned_at>=?
           ORDER BY scanned_at""", (dest, trip_type, window_id, since))]


def deals(conn, window_id, trip_type, region=None):
    """Latest min price per destination vs the median of the previous 14 days.

    Returns dicts: fare (hydrated), trend (list of prices, 14 days), baseline, drop_pct, tracking (bool),
    points ([(scanned_at, price)], 30 days, for the price-trend chart).
    Sorted by drop_pct desc; 'tracking' routes (< MIN_POINTS history) follow, cheapest first.
    """
    scan = latest_scan(conn)
    if not scan:
        return []
    rows = conn.execute(
        """SELECT * FROM fares WHERE scan_id=? AND window_id=? AND trip_type=? AND scan_mode='nonstop'
           AND stops=0 AND status='ready_to_publish' ORDER BY price_usd""",
        (scan["scan_id"], window_id, trip_type)).fetchall()
    best = {}
    for r in rows:
        best.setdefault(r["destination"], r)
    out = []
    for dest, r in best.items():
        d = config.destination(dest) or {}
        if region and d.get("region") != region:
            continue
        # 30 days for the chart's 7/14/30-day views; the baseline and `trend` stay on the last 14.
        hist30 = history(conn, dest, trip_type, window_id, days=30, until=scan["scanned_at"])
        cutoff = (datetime.fromisoformat(scan["scanned_at"][:19]) - timedelta(days=BASELINE_DAYS)).isoformat()
        hist = [h for h in hist30 if h["scanned_at"] >= cutoff]
        prev = [h["min_price"] for h in hist if h["scanned_at"] < scan["scanned_at"]]
        tracking = len(prev) < MIN_POINTS
        baseline = statistics.median(prev) if not tracking else None
        drop = (baseline - r["price_usd"]) / baseline if baseline else None
        fare = hydrate(conn, r)
        fare["fare_id"] = str(r["id"])
        out.append({"fare": fare, "trend": [h["min_price"] for h in hist], "baseline": baseline,
                    "drop_pct": drop, "tracking": tracking,
                    "points": [(h["scanned_at"], h["min_price"]) for h in hist30]})
    ranked = sorted((x for x in out if not x["tracking"]), key=lambda x: -(x["drop_pct"] or 0))
    tracking = sorted((x for x in out if x["tracking"]), key=lambda x: x["fare"]["price_usd"])
    return ranked + tracking


# ---------------------------------------------------------------- Airline Matrix
def _recent_cutoff(scan):
    """Oldest scanned_at still counted as current. ISO-formatted like the column, because the values
    compare as text (SQLite's datetime() uses a space instead of 'T', which lets older scans through)."""
    return (datetime.fromisoformat(scan["scanned_at"]) - timedelta(days=1)).isoformat()


def _current_nonstops(conn, airline, trip_type, scan):
    """An airline's nonstops from each route's newest scan, cheapest first. Older scans are skipped even when
    cheaper, so a price that has since gone up never shows; a route the last scan missed keeps its previous one."""
    return _ready(conn, """
        WITH mine AS (SELECT * FROM fares WHERE airline_iata=? AND stops=0 AND trip_type=?
                      AND status='ready_to_publish' AND scanned_at>=?)
        SELECT * FROM mine
        WHERE scanned_at=(SELECT MAX(scanned_at) FROM mine newer WHERE newer.destination=mine.destination)
        ORDER BY price_usd""", (airline, trip_type, _recent_cutoff(scan)))


def airline_routes(conn, airline):
    """Nonstop destinations for an airline: latest scans ∪ destinations.json carriers."""
    dests = {d["iata"] for d in config.destinations() if airline in d.get("carriers", [])}
    scan = latest_scan(conn)
    if scan:
        dests |= {r[0] for r in conn.execute(
            "SELECT DISTINCT destination FROM fares WHERE airline_iata=? AND stops=0 AND scanned_at>=?",
            (airline, _recent_cutoff(scan)))}
    return sorted(dests)


def matrix(conn):
    """One card per airline flying from TPA (seen in a scan or listed as a carrier)."""
    seen = {r[0] for r in conn.execute("SELECT DISTINCT airline_iata FROM fares WHERE stops=0 AND airline_iata IS NOT NULL")}
    carriers = {c for d in config.destinations() for c in d.get("carriers", [])}
    out = []
    for code in sorted(seen | carriers, key=config.airline_name):
        if code not in config.airlines():
            continue
        # Planespotters (real tail photo) first, then the most-flown type's Commons photo,
        # then any cached asset for the airline (ensure_airline_assets fills carriers with no fares).
        row = conn.execute(
            """SELECT a.* FROM assets a LEFT JOIN fares f ON f.asset_key=a.asset_key
               WHERE a.asset_key LIKE ? AND a.exterior_url IS NOT NULL
               GROUP BY a.asset_key
               ORDER BY (a.exterior_source='planespotters') DESC, COUNT(f.id) DESC LIMIT 1""",
            (f"{code}|%",)).fetchone()
        info = config.airline(code)
        out.append({"iata": code, "name": config.airline_name(code), "n_nonstops": len(airline_routes(conn, code)),
                    "status": info.get("status"), "operating": info.get("operating", True),
                    "asset": dict(row) if row else config.load_json("exteriors.json").get(code, {})})
    return out


def airline_photo_asset(conn, airline):
    """Most-used asset row for an airline (for the photo library), preferring rows with photos."""
    row = conn.execute(
        """SELECT a.* FROM fares f JOIN assets a ON a.asset_key=f.asset_key WHERE f.airline_iata=?
           GROUP BY a.asset_key
           ORDER BY (a.exterior_url IS NOT NULL) + (a.interior_url IS NOT NULL) + (a.seat_url IS NOT NULL)
                    + (a.food_url IS NOT NULL) DESC, COUNT(*) DESC LIMIT 1""", (airline,)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM assets WHERE asset_key LIKE ? ORDER BY (exterior_url IS NOT NULL) DESC, asset_key LIMIT 1", (f"{airline}|%",)).fetchone()
    asset = dict(row) if row else config.load_json("exteriors.json").get(airline, {})
    aircraft = asset.get("asset_key", "|").split("|", 1)[1]
    return {**asset, **curated_photos(airline, aircraft)}


def airline_review(conn, airline):
    return review_summary(conn, f"{airline}|*")


def route_prices(conn, airline):
    """Cheapest one-way nonstop per destination in the latest scan, cheapest first ('Routes from TPA')."""
    scan = latest_scan(conn)
    if not scan:
        return []
    seen = {}
    for f in _current_nonstops(conn, airline, "one_way", scan):
        seen.setdefault(f["destination"], f)
    return list(seen.values())


def airline_deals(conn, airline, trip_type="one_way"):
    """The three 'Deals on [airline]' cards (V5.1 p7) for one trip type; any of them can be None.

    Scans only collect fares with stops for one-way trips, so a round-trip 'cheapest' is drawn from nonstops."""
    nonstop, with_stops = [], []
    scan, any_scan = latest_scan(conn), latest_scan(conn, "any")
    if scan:
        nonstop = _current_nonstops(conn, airline, trip_type, scan)
    if any_scan:
        with_stops = _ready(conn, """SELECT * FROM fares WHERE scan_id=? AND airline_iata=? AND stops>0 AND trip_type=?
                                      AND status='ready_to_publish' ORDER BY price_usd LIMIT 1""",
                            (any_scan["scan_id"], airline, trip_type))
    timed = [f for f in nonstop if f.get("duration_min")]
    return {"cheapest": min(nonstop[:1] + with_stops, key=lambda f: f["price_usd"], default=None),
            "fastest_nonstop": min(timed, key=lambda f: (f["duration_min"], f["price_usd"]), default=None),
            "cheapest_nonstop": nonstop[0] if nonstop else None}


def ontime_pct(conn, airline, dest):
    """Latest BTS on-time % for TPA -> dest on this airline (None until delay data is loaded)."""
    row = conn.execute("""SELECT ontime_pct FROM delay_stats WHERE airline_iata=? AND origin='TPA' AND dest=?
                          AND ontime_pct IS NOT NULL ORDER BY period DESC LIMIT 1""", (airline, dest)).fetchone()
    return row[0] if row else None
