"""Airport reference lookups (OurAirports CSV) and haversine distance."""
import csv
import math
from functools import lru_cache

from core.config import DATA_DIR

AIRPORTS_CSV = DATA_DIR / "airports.csv"

# Metro names in review route text that cover several airports.
METRO_ALIASES = {
    "new york": {"JFK", "LGA", "EWR"},
    "nyc": {"JFK", "LGA", "EWR"},
    "washington": {"DCA", "IAD", "BWI"},
    "washington dc": {"DCA", "IAD", "BWI"},
    "chicago": {"ORD", "MDW"},
    "houston": {"IAH", "HOU"},
    "dallas": {"DFW", "DAL"},
    "dallas fort worth": {"DFW", "DAL"},
    "los angeles": {"LAX"},
    "san francisco": {"SFO"},
    "tampa": {"TPA"},
    "st petersburg": {"PIE"},
    "fort lauderdale": {"FLL"},
    "minneapolis": {"MSP"},
    "detroit": {"DTW"},
    "boston": {"BOS"},
    "atlanta": {"ATL"},
    "denver": {"DEN"},
    "charlotte": {"CLT"},
    "philadelphia": {"PHL"},
    "baltimore": {"BWI"},
    "newark": {"EWR"},
}


@lru_cache(maxsize=1)
def airports():
    """IATA -> {name, city, lat, lon, country, scheduled}. Empty if the CSV isn't downloaded."""
    out = {}
    if not AIRPORTS_CSV.exists():
        return out
    with open(AIRPORTS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iata = (row.get("iata_code") or "").strip().upper()
            if len(iata) != 3 or row.get("type") == "closed":
                continue
            try:
                lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
            except (TypeError, ValueError):
                continue
            prev = out.get(iata)
            scheduled = row.get("scheduled_service") == "yes"
            if prev and prev["scheduled"] and not scheduled:
                continue
            out[iata] = {
                "iata": iata,
                "name": row.get("name", ""),
                "city": row.get("municipality", ""),
                "country": row.get("iso_country", ""),
                "type": row.get("type", ""),
                "lat": lat,
                "lon": lon,
                "scheduled": scheduled,
            }
    return out


@lru_cache(maxsize=1)
def city_index():
    """lower-case city -> set of IATA codes for airports with scheduled service."""
    idx = {}
    for a in airports().values():
        if a["scheduled"] and a["type"] in ("large_airport", "medium_airport") and a["city"]:
            idx.setdefault(_norm(a["city"]), set()).add(a["iata"])
    for k, v in METRO_ALIASES.items():
        idx[k] = set(v)
    return idx


def _norm(s):
    return " ".join("".join(c if c.isalnum() else " " for c in s.lower()).split())


def city_to_iata(text):
    """Map a city name (or bare IATA code) to a set of IATA codes; empty set if unknown."""
    if not text:
        return set()
    t = text.strip()
    if len(t) == 3 and t.isalpha() and t.isupper():
        return {t}
    key = _norm(t)
    idx = city_index()
    if key in idx:
        return idx[key]
    # "Tampa FL", "New York JFK" -> try a trailing IATA code, then leading words
    words = t.split()
    if words and len(words[-1]) == 3 and words[-1].isupper() and words[-1].isalpha():
        return {words[-1]}
    for n in range(len(key.split()) - 1, 0, -1):
        k = " ".join(key.split()[:n])
        if k in idx:
            return idx[k]
    return set()


def haversine_mi(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_mi(a, b):
    ap = airports()
    if a not in ap or b not in ap:
        return None
    return haversine_mi(ap[a]["lat"], ap[a]["lon"], ap[b]["lat"], ap[b]["lon"])
