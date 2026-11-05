"""Glue: the background cycle (Scouter -> Enricher -> Critic -> deals) and the live search chain.

    python -m bots.pipeline --once               # one full scan cycle
    python -m bots.pipeline --dry-run --limit 2  # hit real sources for 2 destinations, print rows, no writes
"""
import argparse
import random
import time
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from bots import critic, enricher, scouter
from core import config
from core.config import settings
from core.db import get_conn
from core.db import utcnow
from core.pricing import Party
from sources import flights_fast, flights_serpapi, news

log = logging.getLogger(__name__)

PRUNE_FARES_DAYS = 30
BUNDLE_OUTBOUNDS = 4  # return searches per bundle view (1 Google request each)


def prune(conn, days=PRUNE_FARES_DAYS):
    """Drop fares older than `days` (price_history is kept forever)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn.execute("DELETE FROM deal_alerts WHERE fare_id IN (SELECT id FROM fares WHERE scanned_at<?)", (cutoff,))
    n = conn.execute("DELETE FROM fares WHERE scanned_at<?", (cutoff,)).rowcount
    conn.commit()
    return n


def run_background_cycle(conn=None, limit=None, dry_run=False):
    conn = conn or get_conn()
    if dry_run:
        rows = scouter.scan(conn, limit=limit, dry_run=True)
        print(f"\n{len(rows)} rows (dry run, nothing written)")
        return None
    scan_id = scouter.scan(conn, limit=limit)
    enriched = enricher.run(conn)
    reviewed = critic.run(conn)
    carriers = sorted({c for d in config.destinations() for c in d.get("carriers", [])})
    enricher.ensure_airline_assets(conn, carriers)
    pruned = prune(conn)
    log.info("cycle %s: enriched=%d reviewed=%d pruned=%d", scan_id, enriched, reviewed, pruned)
    return scan_id


def live_search(conn, origin, dest, depart, ret=None, nonstop=True, party=1):
    """Scouter (live): fast-flights first, SerpApi fallback if the quota allows. No `fares` writes."""
    try:
        return flights_fast.search(origin, dest, depart, ret, nonstop, party), "fast_flights", None
    except flights_fast.SearchFailed as e:
        log.warning("live fast-flights failed: %s", e)
    unavailable = "Live search unavailable — try again later"
    if not flights_serpapi.available():
        return [], None, unavailable
    try:
        return flights_serpapi.search(conn, origin, dest, depart, ret, nonstop, party), "serpapi", None
    except Exception as e:  # QuotaExceeded, network, API error
        log.warning("live serpapi failed: %s", e)
        return [], None, unavailable


def fare_id_for(params, fare, extra=""):
    raw = json.dumps([params.get("destination"), params.get("depart_date"), params.get("return_date"),
                      params.get("party"), fare.get("flight_numbers"), fare.get("depart_time"),
                      fare.get("price_usd"), extra], sort_keys=True, default=str)
    return "L" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def save_live_result(conn, fare):
    conn.execute(
        """INSERT INTO live_results(fare_id, payload_json, created_at) VALUES (?,?,?)
           ON CONFLICT(fare_id) DO UPDATE SET payload_json=excluded.payload_json, created_at=excluded.created_at""",
        (fare["fare_id"], json.dumps(fare, default=str), utcnow()))


def _finish(conn, fares, params, party, extra=""):
    """Enricher + Critic on live rows, then save each so its Cabin experience view is linkable."""
    for f in fares:
        f["travelers"] = party.size
        f["party"] = party.as_dict()
        enricher.enrich_fare(conn, f)
        critic.review_fare(conn, f)
        f["fare_id"] = fare_id_for(params, f, extra)
        save_live_result(conn, f)
    conn.commit()
    return fares


def run_live_chain(params, conn=None, progress=None):
    """params: {destination, depart_date, return_date|None, nonstop, party}. Returns {fares, source, error}.

    For round trips, `fares` are the outbound choices priced as the cheapest full round trip.
    """
    conn = conn or get_conn()
    step = progress or (lambda msg: None)
    party = Party.coerce(params.get("party") or params.get("travelers"))
    nonstop = params.get("nonstop", True)
    step("Scouter: searching live fares…")
    fares, source, error = live_search(conn, settings.ORIGIN, params["destination"], params["depart_date"],
                                       params.get("return_date"), nonstop, party)
    if nonstop:
        fares = [f for f in fares if f["stops"] == 0]
    fares.sort(key=lambda f: f["price_usd"])
    for f in fares:
        f["leg"] = "outbound"
    step(f"Enricher + Critic: photos, amenities and reviews for {len(fares)} flights…")
    _finish(conn, fares, params, party)
    return {"fares": fares, "source": source, "error": error}


def run_return_chain(params, outbound, conn=None):
    """Return choices for a chosen outbound, each priced as the full round-trip total."""
    conn = conn or get_conn()
    party = Party.coerce(params.get("party"))
    try:
        rows = flights_fast.search_returns(outbound, party, params.get("nonstop", True))
    except flights_fast.SearchFailed as e:
        log.warning("return search failed: %s", e)
        return {"fares": [], "error": "Return flights unavailable right now — try again or use Book now on Google."}
    rows.sort(key=lambda f: f["price_usd"])
    _finish(conn, rows, params, party, extra=f"ret:{outbound.get('flight_numbers')}")
    return {"fares": rows, "error": None}


def bundle_outbounds(outbounds, k=BUNDLE_OUTBOUNDS):
    """Outbounds to price returns for: cheapest per airline first, then cheapest overall, up to k."""
    picked, seen = [], set()
    for f in outbounds:
        if f.get("airline_iata") not in seen:
            picked.append(f)
            seen.add(f.get("airline_iata"))
    for f in outbounds:
        if len(picked) >= k:
            break
        if f not in picked:
            picked.append(f)
    return picked[:k]


def run_bundle_chain(params, outbounds, conn=None, progress=None):
    """Complete round trips priced together: for a few outbounds, fetch their return choices.

    Each request is spaced like the Scouter (polite to Google). Returns {bundles, error}.
    """
    conn = conn or get_conn()
    step = progress or (lambda msg: None)
    bundles, errors = [], 0
    picks = bundle_outbounds(outbounds)
    for i, out in enumerate(picks):
        step(f"Pricing returns for {out.get('flight_numbers') or 'outbound'} ({i + 1}/{len(picks)})…")
        res = run_return_chain(params, out, conn)
        errors += bool(res["error"])
        for ret in res["fares"]:
            bundles.append({"out": out, "ret": ret, "total": ret["price_usd"]})
        if i < len(picks) - 1:
            time.sleep(random.uniform(1.0, 2.0))
    error = "Some return flights couldn't be priced." if errors and bundles else (
        "Round-trip bundles unavailable right now — try Separate legs." if errors else None)
    return {"bundles": bundles, "error": error}


def refresh_news(conn=None):
    conn = conn or get_conn()
    n = news.refresh_all(conn)
    log.info("news refreshed for %d airlines", n)
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run one full background cycle")
    ap.add_argument("--dry-run", action="store_true", help="print scan rows without writing to the DB")
    ap.add_argument("--limit", type=int, help="only scan the first N destinations")
    ap.add_argument("--news", action="store_true", help="refresh airline news headlines")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("primp").setLevel(logging.WARNING)
    if not (args.once or args.dry_run or args.news):
        ap.error("pass --once, --dry-run or --news")
    if args.news:
        refresh_news()
    if args.once or args.dry_run:
        run_background_cycle(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
