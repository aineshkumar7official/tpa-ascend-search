"""Planespotters.net photo API (by registration). Free, no key; credit + link required."""
import logging

import requests

from core.config import settings
from core.db import cache_get, cache_set

log = logging.getLogger(__name__)

URL = "https://api.planespotters.net/pub/photos/reg/{reg}"
CACHE_DAYS = 30  # "cached per tail forever (re-check monthly)"


def parse(payload):
    photos = (payload or {}).get("photos", [])
    if not photos:
        return None
    p = photos[0]
    return {
        "url": p["thumbnail_large"]["src"],
        "link": p["link"],  # the image must link to this page
        "credit": f"© {p['photographer']} / Planespotters.net",
        "source": "planespotters",
    }


def by_registration(reg, conn=None):
    if not reg:
        return None
    key = f"planespotters:{reg.upper()}"
    if conn is not None:
        hit, value = cache_get(conn, key, CACHE_DAYS)
        if hit:
            return value
    try:
        r = requests.get(URL.format(reg=reg), headers={"User-Agent": settings.HTTP_USER_AGENT}, timeout=10)
        r.raise_for_status()
        result = parse(r.json())
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("planespotters %s failed: %s", reg, e)
        return None  # don't cache transient failures
    if conn is not None:
        cache_set(conn, key, result)
    return result
