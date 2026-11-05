"""Bot 3 — Critic: review summaries per (airline, destination) with route -> airline fallback."""
import logging
from datetime import date, datetime, timedelta, timezone

from core import config
from core.config import settings
from core.db import utcnow
from sources.reviews import highlights

log = logging.getLogger(__name__)

ROUTE_MIN = 3
AIRLINE_MIN = 5
AIRLINE_YEARS = 3
REFRESH_HOURS = 24


def _route_pool(conn, airline, dest, origin=settings.ORIGIN):
    # origin_iata / dest_iata hold comma lists ("JFK,LGA,EWR"), so match on list membership.
    has = lambda col: f"(',' || {col} || ',') LIKE ?"  # noqa: E731
    return [dict(r) for r in conn.execute(
        f"""SELECT * FROM reviews WHERE airline_iata=? AND (
              ({has('origin_iata')} AND {has('dest_iata')}) OR ({has('origin_iata')} AND {has('dest_iata')}))
            ORDER BY review_date DESC""",
        (airline, f"%,{origin},%", f"%,{dest},%", f"%,{dest},%", f"%,{origin},%"),
    )]


def _airline_pool(conn, airline, today=None):
    today = today or date.today()
    cutoff = (today - timedelta(days=365 * AIRLINE_YEARS)).isoformat()
    return [dict(r) for r in conn.execute(
        """SELECT * FROM reviews WHERE airline_iata=? AND (cabin IS NULL OR cabin LIKE 'Economy%')
           AND (review_date IS NULL OR review_date>=?) ORDER BY review_date DESC""",
        (airline, cutoff),
    )]


def pick_fun_fact(airline, today=None):
    facts = config.fun_facts().get(airline or "", [])
    if not facts:
        return None
    today = today or date.today()
    return facts[today.toordinal() % len(facts)]  # rotates daily


def summarize(conn, airline, dest, today=None):
    """Build the review summary for (airline, dest). Returns (review_key, summary dict)."""
    route = _route_pool(conn, airline, dest)
    if len(route) >= ROUTE_MIN:
        level, pool, key = "route", route, f"{airline}|{dest}"
    else:
        airline_pool = _airline_pool(conn, airline, today)
        if len(airline_pool) >= AIRLINE_MIN:
            level, pool, key = "airline", airline_pool, f"{airline}|*"
        else:
            level, pool, key = "none", [], f"{airline}|*"
    ratings = [r["rating_10"] for r in pool if r["rating_10"] is not None]
    sents = [r["sentiment"] for r in pool if r["sentiment"] is not None]
    avg = round(sum(ratings) / len(ratings), 1) if ratings else None
    pros, cons = highlights(pool) if pool else (None, None)
    summary = {
        "review_key": key,
        "match_level": level,
        "avg_rating_10": avg,
        "stars_5": round(avg / 2, 1) if avg is not None else None,
        "review_count": len(pool),
        "sentiment_avg": round(sum(sents) / len(sents), 3) if sents else None,
        "highlight_pros": pros,
        "highlight_cons": cons,
        "sample_review_ids": ",".join(str(r["id"]) for r in pool[:3]) or None,
        "fun_fact": pick_fun_fact(airline, today),
        "computed_at": utcnow(),
    }
    return key, summary


def upsert_summary(conn, s):
    cols = list(s)
    conn.execute(
        f"""INSERT INTO review_summaries ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})
            ON CONFLICT(review_key) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in cols[1:])}""",
        [s[c] for c in cols],
    )


def get_summary(conn, airline, dest):
    """Cached summary for (airline, dest), recomputed when older than REFRESH_HOURS."""
    for key in (f"{airline}|{dest}", f"{airline}|*"):
        row = conn.execute("SELECT * FROM review_summaries WHERE review_key=?", (key,)).fetchone()
        if row:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(row["computed_at"])
            if age < timedelta(hours=REFRESH_HOURS):
                # an airline-level row is only valid if this route still lacks route reviews
                if key.endswith("|*") and len(_route_pool(conn, airline, dest)) >= ROUTE_MIN:
                    break
                return dict(row)
            break
    key, s = summarize(conn, airline, dest)
    upsert_summary(conn, s)
    conn.commit()
    return s


def review_fare(conn, fare):
    """Annotate a fare dict in place (live chain)."""
    fare["review"] = get_summary(conn, fare.get("airline_iata"), fare["destination"])
    fare["review_key"] = fare["review"]["review_key"]
    return fare


def run(conn):
    groups = conn.execute(
        "SELECT airline_iata, destination FROM fares WHERE status='pending_review' GROUP BY airline_iata, destination"
    ).fetchall()
    done = 0
    for g in groups:
        airline, dest = g["airline_iata"], g["destination"]
        where = "status='pending_review' AND airline_iata IS ? AND destination=?"
        try:
            s = get_summary(conn, airline, dest)
            cur = conn.execute(f"UPDATE fares SET review_key=?, status='ready_to_publish' WHERE {where}",
                               (s["review_key"], airline, dest))
            done += cur.rowcount
        except Exception as e:
            log.exception("critic %s|%s failed", airline, dest)
            conn.execute(f"UPDATE fares SET status='error', error=? WHERE {where}", (f"critic: {e}", airline, dest))
        conn.commit()
    return done


def sample_reviews(conn, ids):
    if not ids:
        return []
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if not id_list:
        return []
    q = f"SELECT * FROM reviews WHERE id IN ({','.join('?' * len(id_list))}) ORDER BY review_date DESC"
    return [dict(r) for r in conn.execute(q, id_list)]
