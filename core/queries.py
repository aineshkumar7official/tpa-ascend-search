"""Read-side queries for the web app. Pure functions of a sqlite connection (the UI caches them)."""
import json
import re
import statistics
from datetime import date, datetime, timedelta

from bots.enricher import amenities_for, with_curated
from bots.scouter import BASELINE_DAYS, MIN_POINTS
from core import config
from core.dates import WINDOWS
from core.pricing import distinct_mix, quote
from sources import flights_serpapi

# Deals pill label -> window_id. "Custom" is live-only and never stored.
WINDOW_PILLS = {"Weekend": "wkend+2", "Midweek": "mid+4", "Long weekend": "wkend+6", "Custom": None}
TRIP_PILLS = {"One-way": "one_way", "Round-trip": "round_trip"}

# A stand-out deal is at least this far below the route's typical price for the same departure date.
# Both are required: 10% of a $30 fare is noise, and $20 off a $900 fare isn't much of a deal.
STANDOUT_MIN_DROP = 0.10
STANDOUT_MIN_SAVINGS_USD = 20
STANDOUT_MAX_CARDS = 3  # Ascend Deals shows at most this many stand-outs
# A route still "Tracking" (under MIN_POINTS checks) can be a stand-out once it has this many earlier checks
# for the same departure date and has fallen well below them.
STANDOUT_EARLY_MIN_POINTS = 2


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


# A scan doesn't reach every route: Google blocks some searches and some come back empty. A route the newest scan
# missed keeps the fare from its own newest scan, up to CARRY_FORWARD_DAYS old and only while the flight is still
# ahead, instead of disappearing. An older scan never wins over a newer one for the same route, even when cheaper.
CARRY_FORWARD_DAYS = 3


def _carry_cutoff(scan):
    """Oldest scanned_at still shown. ISO-formatted like the column, because the values compare as text (SQLite's
    datetime() uses a space instead of 'T', which lets older scans through)."""
    return (datetime.fromisoformat(scan["scanned_at"]) - timedelta(days=CARRY_FORWARD_DAYS)).isoformat()


def current_fares(conn, where, args, per, scan=None, mode="nonstop"):
    """Fares matching `where` from each group's newest scan (group = the `per` columns, e.g. 'destination'),
    within CARRY_FORWARD_DAYS of the latest scan and departing no earlier than its date. Rows (not hydrated)."""
    scan = scan or latest_scan(conn, mode)
    if not scan:
        return []
    return conn.execute(f"""
        WITH pool AS (SELECT * FROM fares WHERE {where} AND status='ready_to_publish'
                      AND scanned_at>=? AND depart_date>=?)
        SELECT * FROM pool WHERE scanned_at=(SELECT MAX(scanned_at) FROM pool newer
                                             WHERE {" AND ".join(f"newer.{c} IS pool.{c}" for c in per.split(","))})
        ORDER BY price_usd, return_leg IS NULL""",
        (*args, _carry_cutoff(scan), scan["scanned_at"][:10])).fetchall()


def _mark_carried(f, scan):
    """Note on a fare kept from an earlier scan, so the card can say when its price was checked."""
    if scan and f.get("scanned_at") and f["scanned_at"] < scan["scanned_at"]:
        f["carried_from"] = f["scanned_at"]
    return f


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
    return with_curated(dict(row)) if row else {}


def review_summary(conn, key):
    if not key:
        return None
    row = conn.execute("SELECT * FROM review_summaries WHERE review_key=?", (key,)).fetchone()
    return dict(row) if row else None


def hydrate(conn, fare):
    """Attach asset, review summary and amenities to a fare dict (DB row)."""
    f = dict(fare)
    if f.get("return_leg"):
        f["return_leg"] = json.loads(f["return_leg"])
    f["asset"] = asset(conn, f.get("asset_key"))
    f["review"] = review_summary(conn, f.get("review_key"))
    f["amenities"], f["amenities_typical"] = amenities_for(f.get("airline_iata"), f.get("aircraft_type"),
                                                           (f.get("origin"), f.get("destination")))
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


def _ready(conn, sql, args=None, scan=None):
    """Hydrated fares from a query, or from rows already fetched (pass a list as `sql`)."""
    out = []
    for r in (conn.execute(sql, args) if isinstance(sql, str) else sql):
        f = _mark_carried(hydrate(conn, r), scan)
        f["fare_id"] = str(r["id"])
        out.append(f)
    return out


_HOME_NONSTOPS = "trip_type=? AND scan_mode='nonstop' AND stops=0"


# ---------------------------------------------------------------- Home
def cheapest_nonstops(conn, trip_type="one_way", n=3):
    """Cheapest nonstop per destination from its newest scan (see current_fares), top n by price."""
    scan = latest_scan(conn)
    best = {}
    for r in current_fares(conn, _HOME_NONSTOPS, (trip_type,), "destination", scan):
        best.setdefault(r["destination"], r)  # rows come cheapest first
    rows = sorted(best.values(), key=lambda r: (r["price_usd"], r["depart_date"]))[:n]
    return _ready(conn, rows, scan=scan)


def nonstop_candidates(conn, trip_type="one_way"):
    """Cheapest nonstop per (destination, airline) from each destination's newest scan — the pool Home re-ranks by
    the with-bags total when 'Bags included' is on (a low fare with high bag fees can lose to another airline).
    Among equal prices the fare with a return flight wins."""
    scan = latest_scan(conn)
    best = {}
    for r in current_fares(conn, _HOME_NONSTOPS, (trip_type,), "destination", scan):
        best.setdefault((r["destination"], r["airline_iata"]), r)  # cheapest first, return flight first on ties
    rows = sorted(best.values(), key=lambda r: (r["price_usd"], r["depart_date"]))
    return _ready(conn, rows, scan=scan)


def cheapest_mix(conn, trip_type="one_way", n=3):
    """Home cards: the cheapest nonstops in the latest scan with no airline and no city repeated."""
    return distinct_mix(nonstop_candidates(conn, trip_type), n)  # candidates are already cheapest first


# ---------------------------------------------------------------- Deals
def history(conn, dest, trip_type, window_id, depart_date, days=BASELINE_DAYS, until=None):
    """Price checks for one departure date. Windows roll forward, and prices for different dates aren't comparable."""
    until = until or datetime.utcnow().isoformat()
    since = (datetime.fromisoformat(until[:19]) - timedelta(days=days)).isoformat()
    return [dict(r) for r in conn.execute(
        """SELECT scanned_at, min_price FROM price_history
           WHERE destination=? AND trip_type=? AND window_id=? AND depart_date=? AND nonstop_only=1 AND scanned_at>=?
           ORDER BY scanned_at""", (dest, trip_type, window_id, depart_date, since))]


def deals(conn, window_id, trip_type, region=None, carry_on=0, checked=0, party=1):
    """Latest min price per destination vs the median of up to 14 days of checks for the same departure date.

    With bags picked, each destination's fare is the cheapest total with bags, and fares whose bag fees
    are unknown are left out.

    Returns dicts: fare (hydrated), trend (list of prices, 14 days), baseline, drop_pct, tracking (bool),
    points ([(scanned_at, price)], 30 days, for the price-trend chart).
    Sorted by drop_pct desc; 'tracking' routes (< MIN_POINTS history) follow, cheapest first.
    """
    scan = latest_scan(conn)
    if not scan:
        return []
    # Each destination's newest scan in this window (a destination the latest scan missed keeps its last fare).
    rows = current_fares(conn, "window_id=? AND trip_type=? AND scan_mode='nonstop' AND stops=0",
                         (window_id, trip_type), "destination", scan)
    if carry_on or checked:
        quotes = [(r, quote(dict(r), carry_on, checked, party)) for r in rows]
        priced = sorted((x for x in quotes if x[1].bags_total is not None), key=lambda x: x[1].total)
        rows = [r for r, _ in priced]
    best = {}
    for r in rows:
        best.setdefault(r["destination"], r)
    out = []
    for dest, r in best.items():
        d = config.destination(dest) or {}
        if region and d.get("region") != region:
            continue
        # 30 days for the chart's 7/14/30-day views; the baseline and `trend` stay on the last 14.
        at = r["scanned_at"]  # the fare's own scan: older than the latest one when carried forward
        hist30 = history(conn, dest, trip_type, window_id, r["depart_date"], days=30, until=at)
        cutoff = (datetime.fromisoformat(at[:19]) - timedelta(days=BASELINE_DAYS)).isoformat()
        hist = [h for h in hist30 if h["scanned_at"] >= cutoff]
        prev = [h["min_price"] for h in hist if h["scanned_at"] < at]
        tracking = len(prev) < MIN_POINTS
        baseline = statistics.median(prev) if not tracking else None
        drop = (baseline - r["price_usd"]) / baseline if baseline else None
        fare = _mark_carried(hydrate(conn, r), scan)
        fare["fare_id"] = str(r["id"])
        out.append({"fare": fare, "trend": [h["min_price"] for h in hist], "baseline": baseline,
                    "drop_pct": drop, "tracking": tracking, "prev": prev,
                    "points": [(h["scanned_at"], h["min_price"]) for h in hist30]})
    ranked = sorted((x for x in out if not x["tracking"]), key=lambda x: -(x["drop_pct"] or 0))
    tracking = sorted((x for x in out if x["tracking"]), key=lambda x: x["fare"]["price_usd"])
    return ranked + tracking


def standout_drop(deal):
    """How a deal qualifies as a stand-out, or None: {"pct", "ref", "basis"}.

    Every basis needs the same 10% and $20 fall, checked in this order:
      typical  below the median of the last 14 days of checks (needs MIN_POINTS of them)
      early    still Tracking, but below the median of its STANDOUT_EARLY_MIN_POINTS+ earlier checks
      last     below the previous check (a sharp fall the 14-day median hasn't caught up with)
    All of them compare prices for the same departure date only.
    """
    price = deal["fare"]["price_usd"]
    prev = deal.get("prev") or []

    def fell(ref, basis):
        if ref and (ref - price) / ref >= STANDOUT_MIN_DROP and ref - price >= STANDOUT_MIN_SAVINGS_USD:
            return {"pct": (ref - price) / ref, "ref": ref, "basis": basis}
        return None

    if not deal["tracking"] and deal["baseline"]:
        hit = fell(deal["baseline"], "typical")
        if hit:
            return hit
    if deal["tracking"] and len(prev) >= STANDOUT_EARLY_MIN_POINTS:
        hit = fell(statistics.median(prev), "early")
        if hit:
            return hit
    return fell(prev[-1], "last") if prev else None


def is_standout(deal):
    return standout_drop(deal) is not None


def standout_deals(conn, trip_type, region=None, carry_on=0, checked=0, party=1):
    """Stand-out deals of one trip type across every date window, biggest drop first.

    Each is a `deals()` dict plus window_label (which window it came from) and standout (see standout_drop).
    """
    out = []
    for window_label, window_id in WINDOW_PILLS.items():
        if window_id is None:  # Custom is live-only, so it has no price history
            continue
        for d in deals(conn, window_id, trip_type, region, carry_on, checked, party):
            hit = standout_drop(d)
            if hit:
                out.append({**d, "window_label": window_label, "standout": hit})
    return sorted(out, key=lambda d: -d["standout"]["pct"])


def standouts_to_show(standouts, home_destinations, n=STANDOUT_MAX_CARDS):
    """The stand-outs Ascend Deals shows: the n biggest drops, skipping any city already on the Home cards
    so the two pages never feature the same deal."""
    def city(iata):  # JFK/LGA/EWR count as one city, as on Home
        return config.metro_for(iata) or iata

    home = {city(x) for x in home_destinations}
    return [d for d in standouts if city(d["fare"]["destination"]) not in home][:n]


# ---------------------------------------------------------------- Airline Matrix
def _current_nonstops(conn, airline, trip_type, scan):
    """An airline's nonstops from each route's newest scan, cheapest first (see current_fares)."""
    return _ready(conn, current_fares(conn, "airline_iata=? AND stops=0 AND trip_type=?", (airline, trip_type),
                                      "destination", scan), scan=scan)


def airline_routes(conn, airline):
    """Nonstop destinations for an airline: latest scans ∪ destinations.json carriers."""
    dests = {d["iata"] for d in config.destinations() if airline in d.get("carriers", [])}
    scan = latest_scan(conn)
    if scan:
        dests |= {r[0] for r in conn.execute(
            "SELECT DISTINCT destination FROM fares WHERE airline_iata=? AND stops=0 AND scanned_at>=?",
            (airline, _carry_cutoff(scan)))}
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
        # A hand-picked livery photo (cabins.json) wins over the cached one (see with_curated).
        asset = with_curated(dict(row)) if row else {}
        curated = (config.cabins().get(f"{code}|*") or {}).get("exterior") or {}
        if not row and curated.get("image_url"):
            asset = {"exterior_url": curated["image_url"], "exterior_link": curated.get("source_page"),
                     "exterior_credit": curated.get("credit"), "exterior_source": "curated"}
        routes = airline_routes(conn, code)
        out.append({"iata": code, "name": config.airline_name(code), "n_nonstops": len(routes), "routes": routes,
                    "asset": asset})
    return out


# Airline Matrix filters (Wireframes V9.1). Each option -> test on an airline.
MATRIX_SORTS = ("A–Z (default)", "Z–A", "Most nonstops")
AIRLINE_TYPES = {"All airlines": lambda info: True,
                 "Budget": lambda info: info.get("fare_model") == "Budget",
                 "Low-Cost": lambda info: info.get("fare_model") == "Low-Cost",
                 "Full Service": lambda info: info.get("fare_model") == "Full Service",
                 "International": lambda info: bool(info.get("international"))}
DOMESTIC_REGIONS = {"Southeast", "Northeast", "Midwest", "Southwest", "West"}
DESTINATION_TYPES = {
    "All destinations": None,
    "Domestic (U.S.)": DOMESTIC_REGIONS,
    "International": {"Caribbean & Latin America", "Canada", "Europe"},
    "Caribbean & Latin America": {"Caribbean & Latin America"},
    "Canada": {"Canada"},
    "Europe": {"Europe"},
}


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def start_date(note):
    """The first date in a carrier_status note ('Dec 19, 2026', 'June 18, 2027 (year-round)', 'November 2026' = the
    1st), or None when the note has no date."""
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(?:(\d{1,2}),\s*)?(\d{4})", note or "")
    if not m or m.group(1)[:3].lower() not in _MONTHS:
        return None
    return date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2) or 1))


def has_started(airline, iata, today=None):
    """False for a route the airline hasn't started flying yet (carrier_status 'coming_soon' in destinations.json),
    until its start date in the note has passed."""
    cs = ((config.destination(iata) or {}).get("carrier_status") or {}).get(airline) or {}
    if cs.get("status") != "coming_soon":
        return True
    start = start_date(cs.get("note"))
    return bool(start and start <= (today or date.today()))


def matching_routes(airline, routes, regions, today=None):
    """The airline's routes to destinations in `regions` that it already flies (Matrix Destination type filter)."""
    region_of = {d["iata"]: d.get("region") for d in config.destinations()}
    return [r for r in routes if region_of.get(r) in regions and has_started(airline, r, today)]


def destination_regions(dest_type):
    """The regions a Destination type covers, or None for all destinations."""
    return DESTINATION_TYPES.get(dest_type)


def route_cover(conn, airline, regions):
    """A Matrix cover showing the plane the airline flies to those regions (e.g. Delta's A330-900neo to Amsterdam when
    the filter is Europe), or None to keep the usual cover. Only trusted photos are used: one picked for that aircraft
    in cabins.json, or a Planespotters photo of a real tail, never an airline-wide pick or a Commons search result."""
    dests = [d["iata"] for d in config.destinations() if d.get("region") in regions]
    if not dests:
        return None
    row = conn.execute(
        f"""SELECT a.* FROM fares f JOIN assets a ON a.asset_key=f.asset_key
            WHERE f.airline_iata=? AND f.stops=0 AND f.destination IN ({",".join("?" * len(dests))})
            GROUP BY a.asset_key ORDER BY COUNT(*) DESC LIMIT 1""", (airline, *dests)).fetchone()
    if not row:
        return None
    asset = dict(row)
    aircraft = asset["asset_key"].split("|", 1)[1]
    picked = ((config.cabins().get(f"{airline}|{aircraft}") or {}).get("exterior") or {})
    if picked.get("image_url"):
        return {**asset, "exterior_url": picked["image_url"], "exterior_link": picked.get("source_page"),
                "exterior_credit": picked.get("credit"), "exterior_source": "curated"}
    return asset if asset.get("exterior_source") == "planespotters" else None


def filter_matrix(items, sort="A–Z (default)", airline_type="All airlines", dest_type="All destinations"):
    """The Matrix cards for the chosen filters: an airline stays when it is that type and flies nonstop from TPA to
    at least one destination of that type."""
    regions = DESTINATION_TYPES.get(dest_type)
    keep = AIRLINE_TYPES.get(airline_type, AIRLINE_TYPES["All airlines"])  # airlines.json fare_model / international
    out = [a for a in items if keep(config.airline(a["iata"]))
           and (regions is None or matching_routes(a["iata"], a.get("routes", []), regions))]
    if sort == "Z–A":
        return sorted(out, key=lambda a: a["name"].lower(), reverse=True)
    if sort == "Most nonstops":
        return sorted(out, key=lambda a: (-a["n_nonstops"], a["name"].lower()))
    return sorted(out, key=lambda a: a["name"].lower())


def airline_photo_asset(conn, airline):
    """Most-used asset row for an airline (for the photo library), preferring rows with photos."""
    row = conn.execute(
        """SELECT a.* FROM fares f JOIN assets a ON a.asset_key=f.asset_key WHERE f.airline_iata=?
           GROUP BY a.asset_key
           ORDER BY (a.exterior_url IS NOT NULL) + (a.interior_url IS NOT NULL) + (a.seat_url IS NOT NULL)
                    + (a.food_url IS NOT NULL) DESC, COUNT(*) DESC LIMIT 1""", (airline,)).fetchone()
    if row:
        return with_curated(dict(row))
    row = conn.execute("SELECT * FROM assets WHERE asset_key LIKE ? LIMIT 1", (f"{airline}|%",)).fetchone()
    return with_curated(dict(row)) if row else {}


def airline_review(conn, airline):
    return review_summary(conn, f"{airline}|*")


def route_prices(conn, airline, trip_type="one_way"):
    """Cheapest nonstop per destination in the latest scan, cheapest first ('Routes from TPA')."""
    scan = latest_scan(conn)
    if not scan:
        return []
    seen = {}
    for f in _current_nonstops(conn, airline, trip_type, scan):
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
        with_stops = _ready(conn, current_fares(conn, "airline_iata=? AND stops>0 AND trip_type=?", (airline, trip_type),
                                                "destination", any_scan, mode="any")[:1], scan=any_scan)
    timed = [f for f in nonstop if f.get("duration_min")]
    return {"cheapest": min(nonstop[:1] + with_stops, key=lambda f: f["price_usd"], default=None),
            "fastest_nonstop": min(timed, key=lambda f: (f["duration_min"], f["price_usd"]), default=None),
            "cheapest_nonstop": nonstop[0] if nonstop else None}


def ontime_pct(conn, airline, dest):
    """Latest BTS on-time % for TPA -> dest on this airline (None until delay data is loaded)."""
    row = conn.execute("""SELECT ontime_pct FROM delay_stats WHERE airline_iata=? AND origin='TPA' AND dest=?
                          AND ontime_pct IS NOT NULL ORDER BY period DESC LIMIT 1""", (airline, dest)).fetchone()
    return row[0] if row else None
