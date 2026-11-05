"""fast-flights wrapper (pinned to fast-flights 3.1.0).

fast-flights 3.1's own parser skips Google's "top flights" list and drops flight
numbers, so we fetch the HTML with the library and read the raw JS payload here.
`parse_payload()` / `normalize()` are the only places that know Google's shape.
"""
import json
import logging
import re

from fast_flights import FlightQuery, Passengers, create_query, fetch_flights_html
from fast_flights.fetcher import URL as GOOGLE_FLIGHTS_URL
from primp import Client
from selectolax.lexbor import LexborHTMLParser

from core.config import resolve_airline

log = logging.getLogger(__name__)


class SearchFailed(RuntimeError):
    pass


def build_query(origin, dest, depart, ret=None, nonstop=True, party=1):
    from core.pricing import Party

    p = Party.coerce(party)
    max_stops = 0 if nonstop else None
    legs = [FlightQuery(date=depart, from_airport=origin, to_airport=dest, max_stops=max_stops)]
    trip = "one-way"
    if ret:
        legs.append(FlightQuery(date=ret, from_airport=dest, to_airport=origin, max_stops=max_stops))
        trip = "round-trip"
    return create_query(flights=legs, trip=trip, seat="economy",
                        passengers=Passengers(adults=p.adults, children=p.children, infants_on_lap=p.infants), currency="USD", language="en")


def extract_payload(html):
    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        raise SearchFailed("no results script in page (blocked or consent page?)")
    js = script.text()
    data = js.split("data:", 1)[1].rsplit(",", 1)[0]
    if data.endswith("errorHasStatus: true"):
        return None  # Google says: no flights
    return json.loads(data)


def _hhmm(t):
    padded = [*(t or []), None, None]
    return f"{padded[0] or 0:02d}:{padded[1] or 0:02d}"


def clean_aircraft(name):
    if not name:
        return None
    name = re.sub(r"\s*\([^)]*\)", "", name.strip())         # "(Scimitar Winglets)"
    name = re.sub(r"\s+(Passenger|Pax)$", "", name, flags=re.I)
    name = re.sub(r"(\d)MAX", r"\1 MAX", name)
    return name


def _leg_date(leg):
    try:
        y, m, d = leg[20][:3]
        return f"{y:04d}-{m:02d}-{d:02d}"
    except (IndexError, TypeError, ValueError):
        return None


def _segments(legs, depart):
    out = []
    for leg in legs:
        fn = leg[22] if len(leg) > 22 else None
        if not (fn and fn[0] and fn[1]):
            return None
        out.append({"from": leg[3], "to": leg[6], "date": _leg_date(leg) or depart, "flight": f"{fn[0]}{fn[1]}"})
    return out


def _itineraries(payload):
    """Yield (itinerary, price) from the 'top flights' and 'other flights' lists."""
    for idx in (2, 3):
        block = payload[idx] if len(payload) > idx else None
        if not block or not block[0]:
            continue
        for k in block[0]:
            try:
                price = k[1][0][1]
            except (IndexError, TypeError):
                price = None
            yield k[0], price


def normalize(payload, origin, dest, depart, ret=None, search_url=None):
    """Map a raw Google Flights payload to fare dicts (same keys as flights_serpapi.normalize)."""
    if not payload:
        return []
    out, seen = [], set()
    for it, price in _itineraries(payload):
        legs = it[2] or []
        if price is None or not legs:
            continue
        numbers = []
        for leg in legs:
            fn = leg[22] if len(leg) > 22 else None
            if fn and fn[0] and fn[1]:
                numbers.append(f"{fn[0]}{fn[1]}")
        flight_numbers = ",".join(numbers) or None
        dedupe = (flight_numbers, price, _hhmm(it[5]))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        names = it[1] or []
        iata = it[0] if isinstance(it[0], str) and len(it[0]) == 2 else None
        if not iata:
            first_fn = legs[0][22] if len(legs[0]) > 22 else None
            iata = (first_fn and first_fn[0]) or (names and resolve_airline(names[0]))
        via = [leg[6] for leg in legs[:-1] if len(leg) > 6 and isinstance(leg[6], str)]
        out.append({
            "origin": origin,
            "destination": dest,
            "trip_type": "round_trip" if ret else "one_way",
            "depart_date": depart,
            "return_date": ret,
            "stops": len(legs) - 1,
            "price_usd": float(price),
            "airline_iata": iata,
            "airline_name": ", ".join(names) or None,
            "flight_numbers": flight_numbers,
            "aircraft_type": clean_aircraft(legs[0][17] if len(legs[0]) > 17 else None),
            "depart_time": _hhmm(it[5]),
            "arrive_time": _hhmm(it[8]),
            "duration_min": it[9],
            "via_airports": ",".join(via) or None,
            "segments": _segments(legs, depart),
            "search_url": search_url,
            "source": "fast_flights",
        })
    return out


def search(origin, dest, depart, ret=None, nonstop=True, party=1):
    """Google Flights search. Prices are the total for the whole party. Raises SearchFailed.

    For round trips the list is the *outbound* choices, each priced as the cheapest full round trip.
    """
    q = build_query(origin, dest, depart, ret, nonstop, party)
    return _run(lambda: fetch_flights_html(q), origin, dest, depart, ret, q.url())


def search_returns(outbound, party=1, nonstop=True):
    """Return-flight choices for a chosen round-trip outbound (Google's "Choose return" step).

    Each row is a return leg priced as the full round-trip total with `outbound`. Raises SearchFailed.
    """
    from core.booking import encode

    tfs = encode(outbound, party)
    if not tfs:
        raise SearchFailed("outbound has no flight numbers to select")
    origin, dest = outbound.get("origin") or "TPA", outbound["destination"]

    def fetch():
        client = Client(impersonate="chrome_145", impersonate_os="macos", referer=True, cookie_store=True)
        return client.get(GOOGLE_FLIGHTS_URL, params={"tfs": tfs, "hl": "en", "curr": "USD"}).text

    rows = _run(fetch, dest, origin, outbound["return_date"], None, f"{GOOGLE_FLIGHTS_URL}/search?tfs={tfs}&hl=en&curr=USD")
    if nonstop:
        rows = [r for r in rows if r["stops"] == 0]
    for r in rows:
        r["trip_type"] = "round_trip"   # price is the round-trip total
        r["leg"] = "return"
    return rows


def _run(fetch, origin, dest, depart, ret, search_url):
    try:
        html = fetch()
        payload = extract_payload(html)
    except SearchFailed:
        raise
    except Exception as e:  # network errors, layout changes
        raise SearchFailed(f"{type(e).__name__}: {e}") from e
    try:
        return normalize(payload, origin, dest, depart, ret, search_url=search_url)
    except (IndexError, TypeError, KeyError) as e:
        raise SearchFailed(f"payload shape changed: {e}") from e
