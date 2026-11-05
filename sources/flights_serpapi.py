"""SerpApi Google Flights wrapper + monthly quota guard.

Used only for (a) "Get booking links" clicks and (b) live search when fast-flights fails.
"""
import logging
from datetime import datetime, timezone

import requests

from core.config import resolve_airline, settings

log = logging.getLogger(__name__)

API = "https://serpapi.com/search.json"
PROVIDER = "serpapi"


class QuotaExceeded(RuntimeError):
    pass


def _month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def used(conn, provider=PROVIDER):
    row = conn.execute("SELECT calls FROM api_usage WHERE provider=? AND month=?", (provider, _month())).fetchone()
    return row[0] if row else 0


def remaining(conn, budget=None, provider=PROVIDER):
    budget = settings.SERPAPI_MONTHLY_BUDGET if budget is None else budget
    return max(0, budget - used(conn, provider))


def spend(conn, provider: str = PROVIDER, budget: int | None = None) -> bool:
    """Record one call; refuse (False) once the monthly budget is hit."""
    budget = settings.SERPAPI_MONTHLY_BUDGET if budget is None else budget
    if used(conn, provider) >= budget:
        return False
    conn.execute(
        """INSERT INTO api_usage(provider, month, calls) VALUES(?,?,1)
           ON CONFLICT(provider, month) DO UPDATE SET calls = calls + 1""",
        (provider, _month()),
    )
    conn.commit()
    return True


def available():
    return bool(settings.SERPAPI_API_KEY)


def _call(conn, params):
    if not available():
        raise QuotaExceeded("SERPAPI_API_KEY not set")
    if not spend(conn):
        raise QuotaExceeded("SerpApi monthly budget reached")
    params = {"engine": "google_flights", "currency": "USD", "hl": "en",
              "api_key": settings.SERPAPI_API_KEY, **params}
    r = requests.get(API, params=params, headers={"User-Agent": settings.HTTP_USER_AGENT}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data


def _params(origin, dest, depart, ret=None, nonstop=True, party=1):
    from core.pricing import Party

    pt = Party.coerce(party)
    p = {"departure_id": origin, "arrival_id": dest, "outbound_date": depart,
         "type": 1 if ret else 2, "adults": pt.adults, "children": pt.children, "infants_on_lap": pt.infants}
    if ret:
        p["return_date"] = ret
    if nonstop:
        p["stops"] = 1  # 1 = nonstop only
    return p


def _hhmm(ts):
    # "2026-11-13 06:05" -> "06:05"
    return ts.split(" ")[-1] if ts else None


def normalize(data, origin, dest, depart, ret=None):
    """Map a SerpApi response to fare dicts (same keys as flights_fast.normalize)."""
    search_url = (data.get("search_metadata") or {}).get("google_flights_url")
    out = []
    for group in (data.get("best_flights") or []) + (data.get("other_flights") or []):
        legs = group.get("flights") or []
        if not legs or group.get("price") is None:
            continue
        first, last = legs[0], legs[-1]
        names = list(dict.fromkeys(l.get("airline") for l in legs if l.get("airline")))
        iata = resolve_airline(names[0]) if names else None
        if not iata and first.get("flight_number"):
            iata = first["flight_number"].split()[0]
        out.append({
            "origin": origin,
            "destination": dest,
            "trip_type": "round_trip" if ret else "one_way",
            "depart_date": depart,
            "return_date": ret,
            "stops": len(legs) - 1,
            "price_usd": float(group["price"]),
            "airline_iata": iata,
            "airline_name": ", ".join(names) or None,
            "flight_numbers": ",".join(l["flight_number"].replace(" ", "") for l in legs if l.get("flight_number")) or None,
            "aircraft_type": first.get("airplane"),
            "depart_time": _hhmm(first.get("departure_airport", {}).get("time")),
            "arrive_time": _hhmm(last.get("arrival_airport", {}).get("time")),
            "duration_min": group.get("total_duration"),
            "via_airports": ",".join(l.get("arrival_airport", {}).get("id", "") for l in legs[:-1]) or None,
            "logo_url": group.get("airline_logo"),
            "segments": [{"from": l.get("departure_airport", {}).get("id"), "to": l.get("arrival_airport", {}).get("id"),
                          "date": (l.get("departure_airport", {}).get("time") or depart).split(" ")[0],
                          "flight": (l.get("flight_number") or "").replace(" ", "")} for l in legs],
            "search_url": search_url,
            "source": "serpapi",
            "booking_token": group.get("booking_token"),
            "departure_token": group.get("departure_token"),
        })
    return out


def search(conn, origin, dest, depart, ret=None, nonstop=True, party=1):
    """Live search fallback. Spends 1 call."""
    data = _call(conn, _params(origin, dest, depart, ret, nonstop, party))
    return normalize(data, origin, dest, depart, ret)


def calls_needed_for_booking(round_trip):
    return 3 if round_trip else 2


def _match(fares, flight_numbers):
    if flight_numbers:
        for f in fares:
            if f.get("flight_numbers") == flight_numbers:
                return f
    return fares[0] if fares else None


def booking_options(conn, fare):
    """Booking options (airline + OTA links) for one fare.

    One-way: search -> booking_token -> options (2 calls).
    Round-trip: search -> departure_token -> return search -> booking_token -> options (3 calls).
    """
    round_trip = bool(fare.get("return_date"))
    if remaining(conn) < calls_needed_for_booking(round_trip):
        raise QuotaExceeded("Not enough SerpApi budget left this month")
    base = _params(fare["origin"], fare["destination"], fare["depart_date"],
                   fare.get("return_date"), nonstop=(fare.get("stops", 0) == 0))
    data = _call(conn, base)
    outbound_numbers = (fare.get("flight_numbers") or "").split(",")
    pick = _match(normalize(data, fare["origin"], fare["destination"], fare["depart_date"], fare.get("return_date")),
                  fare.get("flight_numbers"))
    if not pick:
        return []
    token = pick.get("booking_token")
    if round_trip and not token and pick.get("departure_token"):
        returns = normalize(_call(conn, {**base, "departure_token": pick["departure_token"]}),
                            fare["origin"], fare["destination"], fare["depart_date"], fare.get("return_date"))
        ret = returns[0] if returns else None
        token = ret and ret.get("booking_token")
    if not token:
        log.info("no booking token for %s (%s)", fare.get("destination"), outbound_numbers)
        return []
    data = _call(conn, {**base, "booking_token": token})
    return parse_booking_options(data)


def parse_booking_options(data):
    out = []
    for opt in data.get("booking_options") or []:
        part = opt.get("together") or opt.get("departing") or {}
        req = part.get("booking_request") or {}
        url = req.get("url")
        if url and req.get("post_data"):
            url = f"{url}?{req['post_data']}"
        out.append({"book_with": part.get("book_with"), "price": part.get("price"), "url": url})
    return out
