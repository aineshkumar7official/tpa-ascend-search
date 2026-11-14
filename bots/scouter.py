"""Bot 1 — Scouter: scans TPA nonstops into `fares` + `price_history`, then flags deals."""
import json
import logging
import random
import statistics
import time
import uuid
from datetime import datetime, timedelta, timezone

from core import config
from core.config import settings
from core.dates import today_local, window_dates, windows as date_windows
from core.db import utcnow
from sources import flights_fast, flights_serpapi

log = logging.getLogger(__name__)

TRIP_TYPES = ("one_way", "round_trip")
ANY_STOPS_WINDOW = "mid+4"   # Airline Matrix "absolute cheapest" scan runs on one window only
FALLBACK_WINDOW = "fallback"  # Airline Matrix: nonstops for airlines the main scan missed (dates: route_scan_dates)
ROUTE_WINDOW = "routes"      # Airline Matrix route prices (scan_routes)
NOT_FLYING_YET = ("coming_soon", "not_flying")  # route scan tries these on Tuesday and Friday only
ROUTE_EXTRA_SEARCHES = 120  # per route scan: days beyond Tuesday/Friday (about 6 minutes at most)
ROUTE_SCAN_EVERY_HOURS = 20  # about daily; pages keep a route's price up to 3 days (queries.CARRY_FORWARD_DAYS)
DROP_THRESHOLD = 0.20
BASELINE_DAYS = 14
MIN_POINTS = 6
PRUNE_AFTER = 3              # consecutive scans with zero nonstops before we flag a route

FARE_COLUMNS = (
    "scan_id", "scanned_at", "origin", "destination", "trip_type", "window_id", "scan_mode",
    "depart_date", "return_date", "stops", "price_usd", "airline_iata", "airline_name",
    "flight_numbers", "aircraft_type", "depart_time", "arrive_time", "duration_min",
    "via_airports", "segments", "search_url", "source", "return_leg",
)
RETURN_LEG_FIELDS = ("airline_iata", "airline_name", "flight_numbers", "depart_date", "depart_time", "arrive_time",
                     "duration_min", "stops", "segments", "origin", "destination", "return_date")


def _sleep():
    time.sleep(random.uniform(*settings.SCAN_DELAY))


def insert_fares(conn, rows, scan_id, scanned_at, window_id, scan_mode):
    for r in rows:
        segs = r.get("segments")
        ret = r.get("return_leg")
        vals = {**r, "segments": json.dumps(segs) if segs else None, "return_leg": json.dumps(ret) if ret else None,
                "scan_id": scan_id, "scanned_at": scanned_at, "window_id": window_id, "scan_mode": scan_mode}
        conn.execute(
            f"INSERT INTO fares ({','.join(FARE_COLUMNS)}) VALUES ({','.join('?' * len(FARE_COLUMNS))})",
            [vals.get(c) for c in FARE_COLUMNS],
        )


def _log_search(conn, scan_id, scanned_at, dest, window_id, trip_type, scan_mode, count, error=None):
    conn.execute(
        "INSERT INTO scan_log VALUES (?,?,?,?,?,?,?,?)",
        (scan_id, scanned_at, dest, window_id, trip_type, scan_mode, count, error),
    )


def attach_return_legs(conn, rows, dest, window_id, scan_id, scanned_at, search_returns):
    """Look up the return flight for the cheapest round trip per airline, so cards can show the whole itinerary.

    Runs right after the outbound search so both are priced together. A return is kept only when its total
    matches the fare: showing it next to a different price would describe a trip that doesn't cost that.
    """
    cheapest = {}
    for r in sorted(rows, key=lambda r: r["price_usd"]):
        cheapest.setdefault(r.get("airline_iata"), r)
    for r in cheapest.values():
        _sleep()
        try:
            returns = sorted(search_returns(r, 1, True), key=lambda x: x["price_usd"])
        except Exception as e:
            log.warning("return leg %s %s %s failed: %s", dest, window_id, r.get("flight_numbers"), e)
            _log_search(conn, scan_id, scanned_at, dest, window_id, "round_trip", "return", 0, str(e))
            continue
        _log_search(conn, scan_id, scanned_at, dest, window_id, "round_trip", "return", len(returns))
        if returns and abs(returns[0]["price_usd"] - r["price_usd"]) < 1:
            r["return_leg"] = {k: returns[0].get(k) for k in RETURN_LEG_FIELDS}
        else:
            log.info("no same-price return for %s %s %s", dest, window_id, r.get("flight_numbers"))


BLOCKED_AFTER = 3          # consecutive fast-flights failures before a scan treats Google as blocking this machine
SERPAPI_SCAN_DESTS = 3     # when blocked: this many destinations, first date window, one-way + round trip


class FallbackSearch:
    """fast-flights first (free, no quota). If Google blocks it (BLOCKED_AFTER failures in a row), the rest of the scan
    uses SerpApi, but only for a small fixed plan (SERPAPI_SCAN_DESTS destinations × the first date window × one-way
    and round trip, nonstop), at most settings.SERPAPI_SCAN_DAILY searches a day, and never into the last
    settings.SERPAPI_RESERVE searches of the monthly budget. Anything outside that plan just fails, like before."""

    def __init__(self, conn, fast=None, serp=None, plan=None):
        self.conn, self.fails, self.blocked = conn, 0, False
        self.fast = fast or flights_fast.search
        self.serp = serp or (lambda *a, **k: flights_serpapi.search(conn, *a, **k))
        if plan is None:
            dests = [d["iata"] for d in config.scan_destinations()][:SERPAPI_SCAN_DESTS]
            first = date_windows()[0]
            plan = {(d, first["depart"]) for d in dests}
        self.plan = plan

    def _day_key(self):
        return f"serpapi_scan_{today_local().isoformat()}"

    def serp_allowed(self):
        if not flights_serpapi.available():
            return False
        if flights_serpapi.remaining(self.conn) <= settings.SERPAPI_RESERVE:
            return False
        return flights_serpapi.used(self.conn, self._day_key()) < settings.SERPAPI_SCAN_DAILY

    def __call__(self, origin, dest, depart, ret=None, nonstop=True, party=1):
        if not self.blocked:
            try:
                rows = self.fast(origin, dest, depart, ret, nonstop=nonstop)
                self.fails = 0
                return rows
            except flights_fast.SearchFailed:
                self.fails += 1
                if self.fails < BLOCKED_AFTER:
                    raise
                self.blocked = True
                log.warning("fast-flights failed %d times in a row: using the SerpApi fallback plan", self.fails)
        if not nonstop or (dest, depart) not in self.plan:
            raise flights_fast.SearchFailed("fast-flights blocked; not in the SerpApi fallback plan")
        if not self.serp_allowed():
            raise flights_fast.SearchFailed("fast-flights blocked; SerpApi daily allowance or reserve reached")
        flights_serpapi.spend(self.conn, self._day_key(), budget=10 ** 6)  # daily counter (the real budget is below)
        return self.serp(origin, dest, depart, ret, nonstop=nonstop, party=party)


def scan(conn, destinations=None, limit=None, dry_run=False, with_any_stops=True, search=None, search_returns=None):
    """Run one scan cycle. Returns the scan_id (or the list of rows when dry_run)."""
    search = search or FallbackSearch(conn)
    search_returns = search_returns or flights_fast.search_returns
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
        except Exception as e:  # FallbackSearch already decided whether SerpApi may be used
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
                if trip_type == "round_trip":
                    attach_return_legs(conn, rows, dest, w["window_id"], scan_id, scanned_at, search_returns)
                insert_fares(conn, rows, scan_id, scanned_at, w["window_id"], mode)
                nonstop = [r["price_usd"] for r in rows if r["stops"] == 0]
                if mode == "nonstop" and nonstop:
                    conn.execute(
                        """INSERT OR REPLACE INTO price_history
                           (destination, trip_type, window_id, scanned_at, min_price, nonstop_only, depart_date)
                           VALUES (?,?,?,?,?,1,?)""",
                        (dest, trip_type, w["window_id"], scanned_at, min(nonstop), w["depart"]),
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
    routes per airline for nonstops, so every airline gets a Matrix photo/deal.

    Searches the route pass's Tuesday and Friday, both ordinary weekdays a few weeks out, and keeps both so the
    deal card shows the cheaper. A single date two weeks out could land on a holiday rush (Nov 21: $945 for a
    flight that was $210). Rows are stored with scan_mode='airline' so they stay out of Home/Deals and price history.
    """
    search = search or flights_fast.search
    routes = {}
    for d in config.destinations():
        for c in d.get("carriers", []):
            if (d.get("carrier_status", {}).get(c) or {}).get("status", "current") == "current":
                routes.setdefault(c, []).append(d["iata"])
    want = {c for c in routes if c not in seen}
    dests = sorted({routes[c][0] for c in want})
    departs = [d.isoformat() for d, _ in route_scan_dates()]
    collected = []
    for dest in dests:
        for depart in departs:
            _sleep()
            try:
                results = search(settings.ORIGIN, dest, depart, None, nonstop=True)
            except Exception as e:
                log.warning("airline fallback %s %s failed: %s", dest, depart, e)
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
    log.info("airline fallback: %d airlines, %d routes searched for %s", len(want), len(dests), ", ".join(departs))
    return collected


def route_scan_dates(today=None, extra=False):
    """(depart, return) to try for a route: the Tuesday of the mid+4 window, then that Friday for airlines
    that don't fly every day. A week away in both cases, so the return is on a day they fly too.

    With `extra`, then the rest of that week (Wed, Thu, Sat, Sun, Mon): many routes run only a few days a week
    (British Airways TPA-LHR skips Tuesdays and Fridays; Breeze flies Bangor and Burlington on Wednesdays and
    Saturdays)."""
    tuesday = window_dates(ANY_STOPS_WINDOW, today or today_local())[0]
    days = (0, 3, 1, 2, 4, 5, 6) if extra else (0, 3)
    return [(tuesday + timedelta(days=n), tuesday + timedelta(days=n + 7)) for n in days]


def _flown_weekdays(conn, dest, airlines):
    """{weekday: count} of past nonstop departures on these airlines to dest, to try their usual days first."""
    marks = ",".join("?" * len(airlines))
    return dict(conn.execute(f"""SELECT CAST(strftime('%w', depart_date) AS INTEGER), COUNT(*) FROM fares
                                 WHERE destination=? AND stops=0 AND airline_iata IN ({marks}) GROUP BY 1""",
                             (dest, *airlines)).fetchall())


def _priced_routes(conn, trip_type, since):
    return {tuple(r) for r in conn.execute(
        "SELECT DISTINCT airline_iata, destination FROM fares WHERE stops=0 AND trip_type=? AND scanned_at>=?",
        (trip_type, since))}


def route_scan_due(conn, hours=ROUTE_SCAN_EVERY_HOURS, now=None):
    now = now or datetime.now(timezone.utc)
    row = conn.execute("SELECT MAX(scanned_at) FROM scan_log WHERE window_id=?", (ROUTE_WINDOW,)).fetchone()
    return not row[0] or datetime.fromisoformat(row[0]) <= now - timedelta(hours=hours)


def scan_routes(conn, search=None, search_returns=None, today=None):
    """Price every airline route in destinations.json that has no recent nonstop fare, for Airline Matrix.

    Only the airlines still missing a price are stored, so this never replaces a main-scan fare. Stored with
    scan_mode='airline', which keeps these out of Home, Deals and price history. Returns the scan_id."""
    search = search or flights_fast.search
    search_returns = search_returns or flights_fast.search_returns
    scan_id, scanned_at = str(uuid.uuid4()), utcnow()
    since = (datetime.fromisoformat(scanned_at) - timedelta(days=1)).isoformat()
    base, week = route_scan_dates(today), route_scan_dates(today, extra=True)
    flies = {}  # dest -> departure dates the one-way search found a missing airline on; round trips try them first
    searched = found = extra_used = 0
    for trip_type in TRIP_TYPES:
        priced = _priced_routes(conn, trip_type, since)
        for d in config.destinations():
            dest = d["iata"]
            missing = {c for c in d.get("carriers", []) if (c, dest) not in priced}
            if trip_type == "one_way":
                # Tuesday and Friday, then the rest of the week for airlines flying (not coming soon / not flying),
                # their usual weekdays first. %w counts Sunday as 0; Python's weekday() counts Monday as 0.
                flying = {c for c in missing if (d.get("carrier_status", {}).get(c) or {}).get("status") not in NOT_FLYING_YET}
                usual = _flown_weekdays(conn, dest, flying) if flying else {}
                rest = sorted(week[len(base):], key=lambda x: -usual.get((x[0].weekday() + 1) % 7, 0))
                dates = base + [(*x, "extra") for x in rest] if flying else base
            else:
                # Days the one-way found (this scan, else the airline's usual weekday this week) a week apart, then
                # Tuesday/Friday; then shorter trips from the first such day, for airlines that fly back only on some
                # days (Southwest flies Memphis Fri-Sun: Friday out, Friday back has no nonstop return).
                flying = {c for c in missing if (d.get("carrier_status", {}).get(c) or {}).get("status") not in NOT_FLYING_YET}
                usual = _flown_weekdays(conn, dest, missing) if missing else {}
                known = flies.get(dest) or [x for x, _ in week if usual.get((x.weekday() + 1) % 7)]
                dates = list(dict.fromkeys([(x, x + timedelta(days=7)) for x in known] + base))
                first = known[0] if known else base[1][0]
                dates += [(first, first + timedelta(days=n), "extra") for n in (2, 3, 4)]
            for depart, ret, *kind in dates:
                if not missing or (kind and not (missing & flying)):
                    break
                if kind:
                    if extra_used >= ROUTE_EXTRA_SEARCHES:
                        break
                    extra_used += 1
                _sleep()
                searched += 1
                back = ret.isoformat() if trip_type == "round_trip" else None
                try:
                    results = search(settings.ORIGIN, dest, depart.isoformat(), back, nonstop=True)
                except Exception as e:
                    log.warning("route scan %s %s failed: %s", dest, trip_type, e)
                    _log_search(conn, scan_id, scanned_at, dest, ROUTE_WINDOW, trip_type, "airline", 0, str(e))
                    conn.commit()
                    continue
                rows = [r for r in results if r["stops"] == 0 and r["airline_iata"] in missing]
                if trip_type == "round_trip":
                    attach_return_legs(conn, rows, dest, ROUTE_WINDOW, scan_id, scanned_at, search_returns)
                insert_fares(conn, rows, scan_id, scanned_at, ROUTE_WINDOW, "airline")
                _log_search(conn, scan_id, scanned_at, dest, ROUTE_WINDOW, trip_type, "airline", len(rows))
                conn.commit()
                missing -= {r["airline_iata"] for r in rows}
                found += len(rows)
                if rows and trip_type == "one_way":
                    flies.setdefault(dest, []).append(depart)
    log.info("route scan %s: %d searches (%d on extra days), %d fares", scan_id, searched, extra_used, found)
    return scan_id


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
        # Windows roll forward, so only prices for this same departure date are comparable.
        key = (ph["destination"], ph["trip_type"], ph["window_id"], ph["depart_date"])
        prev = [r[0] for r in conn.execute(
            """SELECT min_price FROM price_history
               WHERE destination=? AND trip_type=? AND window_id=? AND depart_date=? AND nonstop_only=1
                 AND scanned_at<?""",
            (*key, scanned_at),
        )]
        recent = [r[0] for r in conn.execute(
            """SELECT min_price FROM price_history
               WHERE destination=? AND trip_type=? AND window_id=? AND depart_date=? AND nonstop_only=1
                 AND scanned_at>=? AND scanned_at<?""",
            (*key, since, scanned_at),
        )]
        fare = conn.execute(
            """SELECT id FROM fares WHERE scan_id=? AND destination=? AND trip_type=? AND window_id=?
               AND depart_date=? AND scan_mode='nonstop' AND stops=0 ORDER BY price_usd LIMIT 1""",
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
                   WHERE a.seen=0 AND a.reason=? AND f.destination=? AND f.trip_type=? AND f.window_id=?
                     AND f.depart_date=?""",
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
