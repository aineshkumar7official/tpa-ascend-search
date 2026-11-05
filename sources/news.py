"""Airline news via Google News RSS (headline, source, date, link only — never article text).

Runs once a day from the scheduler; the app only reads `airline_news`. Falls back to data/news.json.
"""
import logging
import re
import time
from urllib.parse import quote_plus

import feedparser
import requests

from core import config
from core.config import settings
from core.db import utcnow

log = logging.getLogger(__name__)

RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
KEEP = 3
KEYWORDS = ("flight", "route", "airline", "airport", "nonstop", "service", "fare", "bag", "seat",
            "aircraft", "jet", "pilot", "passenger", "tampa", "cabin", "lounge", "fleet", "loyalty")


def _query(airline):
    return f'"{config.airline_name(airline)}"'


def relevant(title, airline):
    """Headline must name the airline and mention an aviation keyword."""
    t = (title or "").lower()
    info = config.airline(airline)
    names = [info.get("name", "")] + info.get("aliases", [])
    named = any(n and n.lower() in t for n in names)
    return named and any(k in t for k in KEYWORDS)


def parse(feed_text, airline, keep=KEEP):
    feed = feedparser.parse(feed_text)
    out = []
    for e in feed.entries:
        title = e.get("title", "")
        source = (e.get("source") or {}).get("title")
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        if not relevant(title, airline):
            continue
        published = None
        if e.get("published_parsed"):
            published = time.strftime("%Y-%m-%d", e.published_parsed)
        out.append({"headline": re.sub(r"\s+", " ", title).strip(), "url": e.get("link"),
                    "source": source, "published_at": published})
        if len(out) >= keep:
            break
    return out


def fetch(airline):
    r = requests.get(RSS.format(q=quote_plus(_query(airline))),
                     headers={"User-Agent": settings.HTTP_USER_AGENT}, timeout=15)
    r.raise_for_status()
    return parse(r.text, airline)


def refresh_all(conn, airlines=None, pause=2.0):
    """Daily job: replace each airline's stored headlines. Keeps old rows if the fetch fails."""
    codes = airlines or list(config.airlines())
    done = 0
    for code in codes:
        try:
            items = fetch(code)
        except (requests.RequestException, ValueError) as e:
            log.warning("news %s failed: %s", code, e)
            continue
        if items:
            conn.execute("DELETE FROM airline_news WHERE airline_iata=?", (code,))
            for it in items:
                conn.execute(
                    """INSERT OR IGNORE INTO airline_news(airline_iata, headline, url, source, published_at, fetched_at)
                       VALUES (?,?,?,?,?,?)""",
                    (code, it["headline"], it["url"], it["source"], it["published_at"], utcnow()))
            conn.commit()
            done += 1
        time.sleep(pause)
    return done


def latest(conn, airline, keep=KEEP):
    """Pinned news.json items first, then stored RSS headlines."""
    pinned = [{"headline": n["headline"], "url": n["url"], "source": n.get("source"),
               "published_at": n.get("date")} for n in config.news_pins().get(airline, [])]
    rows = [dict(r) for r in conn.execute(
        """SELECT headline, url, source, published_at FROM airline_news WHERE airline_iata=?
           ORDER BY published_at DESC LIMIT ?""", (airline, keep))]
    return (pinned + rows)[:keep]
