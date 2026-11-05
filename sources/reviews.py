"""Airline review dataset helpers: CSV column mapping, route parsing, sentiment, keyword tallies."""
import re
from datetime import date, datetime

import pandas as pd

from core.config import resolve_airline
from core.geo import city_to_iata

# Kaggle Skytrax/AirlineQuality scrapes use different headers; map them to ours.
COLUMN_ALIASES = {
    "airline_name": ["airline_name", "airline", "airline name", "Airline Name", "Airline"],
    "route_text":   ["route", "Route", "route_text"],
    "cabin":        ["cabin", "seat_type", "Seat Type", "cabin_flown", "Class", "class"],
    "aircraft":     ["aircraft", "Aircraft", "aircraft_type"],
    "rating_10":    ["overall", "overall_rating", "over_all_rating", "Overall_Rating", "Overall Rating", "rating", "Rating"],
    "review_date":  ["review_date", "Review Date", "date", "Date", "date_flown", "Date Flown", "Date Published"],
    "title":        ["header", "review_header", "title", "Title", "Review_Title", "review_title"],
    "body":         ["content", "review_text", "review", "Review", "body", "text", "customer_review", "Review_content"],
}

# Keyword families for "Often praised / Common complaints" (own phrasing, not copied text).
KEYWORD_FAMILIES = {
    "legroom":  r"\blegroom|leg room|seat pitch\b",
    "crew":     r"\bcrew|staff|flight attendants?|cabin attendants?\b",
    "on-time":  r"\bon time|on-time|punctual|delay(?:ed|s)?|late\b",
    "wifi":     r"\bwi-?fi|internet\b",
    "seats":    r"\bseats?\b",
    "boarding": r"\bboarding|gate\b",
    "food":     r"\bfood|snacks?|drinks?|meal\b",
    "bag fees": r"\b(?:bag|baggage|luggage|carry-on|checked bag)s? fees?\b|\bfees? for (?:a |my |the )?(?:bag|baggage|luggage)",
}


def pick_columns(df):
    out = {}
    lower = {c.lower().strip(): c for c in df.columns}
    for target, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            col = a if a in df.columns else lower.get(a.lower())
            if col is not None:
                out[target] = col
                break
    missing = {"airline_name", "body"} - set(out)
    if missing:
        raise ValueError(f"dataset is missing required columns: {sorted(missing)}; found {list(df.columns)}")
    return out


def parse_date(raw):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", str(raw).strip())
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%B %Y", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%b %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return pd.to_datetime(s).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def parse_route(text):
    """'Tampa to New York via Atlanta' -> ({'TPA'}, {'JFK','LGA','EWR'}). Empty sets if unparseable."""
    if not text or not isinstance(text, str):
        return set(), set()
    main = re.split(r"\s+via\s+", text.strip(), maxsplit=1, flags=re.I)[0]
    parts = re.split(r"\s+to\s+|\s+-\s+|\s*→\s*", main, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return set(), set()
    return city_to_iata(parts[0]), city_to_iata(parts[1])


def as_list(iatas):
    return ",".join(sorted(iatas)) if iatas else None


def rating_10(raw):
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if pd.isna(v):
        return None
    return v


_analyzer = None


def sentiment(text):
    global _analyzer
    if _analyzer is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer.polarity_scores(text or "")["compound"]


def unslug(value):
    """Some scrapes store slugs: 'delta-air-lines' -> 'delta air lines', 'tampa,_fl_to_atlanta' -> 'tampa, fl to atlanta'."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v and " " not in v and ("_" in v or "-" in v):
        v = re.sub(r"[_-]+", " ", v)
        v = re.sub(r"\s+,", ",", v)
    return v or None


def read_table(path):
    path = str(path)
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path)


def rows_from_csv(path, max_age_years=5, today=None):
    """Yield dicts ready for the `reviews` table (CSV or Excel)."""
    today = today or date.today()
    df = read_table(path)
    cols = pick_columns(df)
    cutoff = date(today.year - max_age_years, today.month, min(today.day, 28)).isoformat()
    for rec in df.to_dict("records"):
        get = lambda k: rec.get(cols[k]) if k in cols else None  # noqa: E731
        body = get("body")
        name = unslug(get("airline_name"))
        if not isinstance(body, str) or not isinstance(name, str):
            continue
        rdate = parse_date(get("review_date"))
        if rdate and rdate < cutoff:
            continue
        route = unslug(get("route_text"))
        origin, dest = parse_route(route)
        body = re.sub(r"^\s*(✅\s*)?(Trip Verified|Not Verified|Verified Review)\s*\|\s*", "", body).strip()
        title = get("title")
        yield {
            "airline_name": name.title() if name.islower() else name,
            "airline_iata": resolve_airline(name, fuzzy=True),
            "route_text": route,
            "origin_iata": as_list(origin),
            "dest_iata": as_list(dest),
            "cabin": (unslug(get("cabin")) or "").title() or None,
            "aircraft": unslug(get("aircraft")),
            "rating_10": rating_10(get("rating_10")),
            "review_date": rdate,
            "title": title.strip(' "') if isinstance(title, str) else None,
            "body": body,
            "sentiment": sentiment(body),
        }


def keyword_tally(texts):
    counts = {k: 0 for k in KEYWORD_FAMILIES}
    for t in texts:
        low = (t or "").lower()
        for fam, pat in KEYWORD_FAMILIES.items():
            if re.search(pat, low):
                counts[fam] += 1
    return counts


def highlights(pool, top=3, min_share=0.15):
    """Return (pros, cons) phrases from keyword families in positive vs negative reviews."""
    pos = [r["body"] for r in pool if (r["sentiment"] or 0) >= 0.3]
    neg = [r["body"] for r in pool if (r["sentiment"] or 0) <= -0.1]

    def top_fams(texts):
        if not texts:
            return []
        c = keyword_tally(texts)
        ranked = sorted((v, k) for k, v in c.items() if v / len(texts) >= min_share)
        return [k for v, k in reversed(ranked)][:top]

    pros, cons = top_fams(pos), top_fams(neg)
    return (
        f"Often praised: {', '.join(pros)}" if pros else None,
        f"Common complaints: {', '.join(cons)}" if cons else None,
    )
