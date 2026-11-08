"""Settings (from .env), product naming and static-data loaders. Single source of truth for names."""
import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")

# Naming: the wireframes alternate "Ascend Search" / "AscendSearch". Standardized here.
PRODUCT_NAME = "TPA Ascend Search"
BY_LINE = "by AK Aviation"
TAGLINE = "Value the journey"
BANNER_LINE = "Other flights give you the prices; we show you the experience."
NAV_HOME = "Home"
NAV_DEALS = "Ascend Deals"
NAV_MATRIX = "Airline Matrix"
NAV_SEARCH = "Ascend Search"
DISCLAIMER = ("Prices are snapshots from public fare searches and may have changed. "
              "Always confirm on the airline or booking site.")
DISCLAIMER_SHORT = "Prices are snapshots and may have changed. Always confirm on the airline or booking site."
STUDENT_LINE = "Student project · USF"


def _env(name):
    """Environment variable, else a Streamlit Cloud secret of the same name (the deployed app's settings)."""
    if os.getenv(name) is not None:
        return os.getenv(name)
    try:
        from streamlit import runtime

        if not runtime.exists():
            return ""  # scripts, tests, GitHub Actions: no Streamlit secrets
        import streamlit as st

        v = st.secrets.get(name)
        return "" if v is None else str(v)
    except Exception:
        return ""


def _int(name, default):
    raw = _env(name).split("#")[0].strip()
    return int(raw) if raw else default


def _str(name, default):
    raw = _env(name).split(" #")[0].strip()
    return raw or default


class Settings:
    SERPAPI_API_KEY = _str("SERPAPI_API_KEY", "")
    SERPAPI_MONTHLY_BUDGET = _int("SERPAPI_MONTHLY_BUDGET", 90)
    HTTP_USER_AGENT = _str("HTTP_USER_AGENT", "TPA-AscendSearch/0.1 (student project; contact: you@usf.edu)")
    DB_PATH = str(ROOT / _str("DB_PATH", "data/ascend.db"))
    SCAN_INTERVAL_HOURS = _int("SCAN_INTERVAL_HOURS", 6)
    ORIGIN = "TPA"
    ORIGIN_LABEL = "TPA – Tampa"
    TIMEZONE = "America/New_York"
    SCAN_DELAY = (2.0, 4.0)  # fast-flights politeness: seconds between requests (jittered)
    REVIEWS_SOURCE = ("\"Airline Travel Reviews Data (Skytrax)\", Borse & Mishra, Mendeley Data, "
                      "doi:10.17632/vgjk58vf8h.1, CC BY 4.0")
    REVIEWS_SOURCE_URL = "https://data.mendeley.com/datasets/vgjk58vf8h/1"
    POLICY_STALE_DAYS = 45
    FARE_OPTIONS = _str("FARE_OPTIONS", "on")  # "off" skips the local-Chrome lookups of Google's fare options
    DB_DIR = str(ROOT / "data")
    # Deployed app (core/remote_db.py): read the database the scan workflow pushes to this repo's data branch.
    DATA_REPO = _str("DATA_REPO", "")          # "owner/repo"
    DATA_BRANCH = _str("DATA_BRANCH", "data")
    GITHUB_TOKEN = _str("GITHUB_TOKEN", "")    # fine-grained, read-only "Contents" on that repo
    # Quota protection. Scans: SerpApi only when Google blocks fast-flights, at most SERPAPI_SCAN_DAILY searches a day,
    # and never into the last SERPAPI_RESERVE of the monthly budget (kept for testing and the demo).
    SERPAPI_SCAN_DAILY = _int("SERPAPI_SCAN_DAILY", 6)
    SERPAPI_RESERVE = _int("SERPAPI_RESERVE", 50)
    # Live search: "off" never spends SerpApi from the app (the public server), only free fast-flights.
    LIVE_SERPAPI = _str("LIVE_SERPAPI", "on")
    LIVE_SEARCH_DAILY_CAP = _int("LIVE_SEARCH_DAILY_CAP", 0)  # Google requests per day for live search; 0 = no cap


settings = Settings()


@lru_cache(maxsize=None)
def load_json(name):
    path = DATA_DIR / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _public(d):
    """Drop '_note'-style keys."""
    return {k: v for k, v in (d or {}).items() if not k.startswith("_")}


def destinations():
    """All TPA nonstop destinations (Home 'To' dropdown)."""
    return load_json("destinations.json").get("destinations", [])


def scan_destinations():
    """Destinations the background Scouter prices every cycle."""
    return [d for d in destinations() if d.get("scan")]


def destination(iata):
    return next((d for d in destinations() if d["iata"] == iata), None)


# "All airports" groups for the To dropdown (wireframes V4): metro code -> (name, airports).
# Same groupings Google Flights uses; only airports TPA actually flies to (and not 'coming soon') are searched.
# Codes are prefixed "ALL_" so they can never collide with an airport code (Houston's city code HOU is also Hobby).
METROS = {
    "ALL_NYC": ("New York", ["JFK", "LGA", "EWR"]),
    "ALL_CHI": ("Chicago", ["ORD", "MDW"]),
    "ALL_WAS": ("Washington", ["DCA", "IAD", "BWI"]),
    "ALL_HOU": ("Houston", ["IAH", "HOU"]),
    "ALL_DFW": ("Dallas", ["DFW", "DAL"]),
}


def is_metro(code):
    """True for a whole metro ('ALL_NYC') or a ticked part of one ('ALL_NYC:JFK,EWR', wireframes V4 p5)."""
    return code.partition(":")[0] in METROS


def is_metro_subset(code):
    return is_metro(code) and ":" in code


def metro_airports(code):
    """Airports to search for a metro code or subset (or [code] for a single airport)."""
    if not is_metro(code):
        return [code]
    base, _, picked = code.partition(":")
    live = {d["iata"] for d in destinations() if d.get("status") != "coming_soon"}
    airports = [a for a in METROS[base][1] if a in live]
    return [a for a in airports if a in picked.split(",")] if picked else airports


def metro_for(iata):
    return next((m for m, (_, aps) in METROS.items() if iata in aps), None)


def selection_code(airports):
    """Ticked airports of one metro -> destination code: all -> 'ALL_NYC', some -> 'ALL_NYC:JFK,EWR',
    one -> 'JFK', none -> None."""
    picked = list(dict.fromkeys(airports))
    if not picked:
        return None
    if len(picked) == 1:
        return picked[0]
    metro = metro_for(picked[0])
    every = metro_airports(metro)
    ordered = [a for a in every if a in picked]
    return metro if len(ordered) == len(every) else f"{metro}:{','.join(ordered)}"


def city(iata):
    if is_metro(iata):
        return METROS[iata.partition(":")[0]][0]
    d = destination(iata)
    if d:
        return d["city"]
    from core.geo import airports
    return airports().get(iata, {}).get("city") or iata


def regions():
    return sorted({d["region"] for d in destinations() if d.get("region")})


def airlines():
    return _public(load_json("airlines.json"))


def airline(iata):
    return airlines().get(iata or "", {})


def fleet():
    return _public(load_json("fleet.json"))


def cabins():
    return _public(load_json("cabins.json"))


def amenities():
    return _public(load_json("amenities.json"))


def policies():
    return _public(load_json("airline_policies.json"))


def news_pins():
    return _public(load_json("news.json"))


def fun_facts():
    return _public(load_json("fun_facts.json"))


def airline_description(iata):
    """The airline's written description, else the V6 template: where it's from and its alliance. None if neither."""
    info = airline(iata)
    if info.get("description"):
        return info["description"]
    if not info.get("hq"):
        return None
    group = f"part of {info['alliance']}" if info.get("alliance") else "not part of an alliance"
    return f"{info['name']} is based in {info['hq']} and is {group}."


def airline_name(iata):
    return airline(iata).get("name") or iata or "Unknown airline"


def brand_color(iata):
    return airline(iata).get("brand_color", "#5B6470")


def logo_url(iata):
    """Google Flights' hosted logo, linked rather than stored (tpabuildv2.md "Logos").
    Listed airlines only: gstatic answers 200 with a placeholder for unknown codes."""
    return f"https://www.gstatic.com/flights/airline_logos/70px/{iata}.png" if iata in airlines() else None


def resolve_airline(text, fuzzy=False):
    """Map an airline name or IATA code to its IATA code using airlines.json; None if unknown."""
    if not text:
        return None
    t = text.strip()
    known = airlines()
    if t.upper() in known:
        return t.upper()
    low = t.lower()
    for code, info in known.items():
        names = [info.get("name", "")] + info.get("aliases", [])
        if any(low == n.lower() for n in names if n):
            return code
    if fuzzy:
        from rapidfuzz import fuzz, process

        choices = {}
        for code, info in known.items():
            for n in [info.get("name", "")] + info.get("aliases", []):
                if n:
                    choices[n] = code
        hit = process.extractOne(t, list(choices), scorer=fuzz.token_set_ratio, score_cutoff=88)
        if hit:
            return choices[hit[0]]
    return None
