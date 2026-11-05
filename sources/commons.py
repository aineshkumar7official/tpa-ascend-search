"""Wikimedia Commons image search with license filtering and attribution."""
import html
import logging
import re

import requests

from core.config import settings
from core.db import cache_get, cache_set

log = logging.getLogger(__name__)

API = "https://commons.wikimedia.org/w/api.php"
CACHE_DAYS = 30
ALLOWED = ("cc by", "cc-by", "cc0", "public domain", "pd")
INTERIOR_HINTS = ("cabin", "interior", "seat", "economy", "first class", "inside")


def _license_ok(name):
    n = (name or "").lower()
    restricted = set(re.split(r"[\s\-]+", n)) & {"nc", "nd"}
    return n.startswith(ALLOWED) and not restricted


def _strip_html(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _title_words(title):
    return " " + re.sub(r"[^a-z0-9]+", " ", title.lower()) + " "


def parse(payload, kind="exterior", blocked=(), must_contain=()):
    """First reusable image of the right kind. `must_contain`: airline names/codes, one must be in the title."""
    needles = [f" {re.sub(r'[^a-z0-9]+', ' ', n.lower()).strip()} " for n in must_contain if n]
    pages = sorted(((payload or {}).get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    for page in pages:
        title = page.get("title", "")
        if title in blocked or not page.get("imageinfo"):
            continue
        if needles and not any(n in _title_words(title) for n in needles):
            continue
        info = page["imageinfo"][0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not _license_ok(lic):
            continue
        is_interior = any(h in title.lower() for h in INTERIOR_HINTS)
        if kind == "interior" and not is_interior:
            continue
        if kind == "exterior" and is_interior:
            continue
        artist = _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown author"
        return {
            "url": info.get("thumburl") or info.get("url"),
            "link": info.get("descriptionurl"),
            "credit": f"Photo: {artist}, {lic}, via Wikimedia Commons",
            "source": "commons",
        }
    return None


def search(query, kind="exterior", conn=None, blocked=(), must_contain=()):
    key = f"commons:{kind}:{query.lower()}:{'|'.join(sorted(must_contain))}"
    if conn is not None:
        hit, value = cache_get(conn, key, CACHE_DAYS)
        if hit:
            return value
    params = {
        "action": "query", "format": "json",
        "generator": "search", "gsrnamespace": 6, "gsrlimit": 20,
        "gsrsearch": query,
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 800,
    }
    try:
        r = requests.get(API, params=params, headers={"User-Agent": settings.HTTP_USER_AGENT}, timeout=15)
        r.raise_for_status()
        result = parse(r.json(), kind, blocked, must_contain)
    except (requests.RequestException, ValueError) as e:
        log.warning("commons %r failed: %s", query, e)
        return None
    if conn is not None:
        cache_set(conn, key, result)
    return result
