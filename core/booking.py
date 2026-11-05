"""'Book now' links that open Google Flights' booking page for the *specific* fare.

Google's `tfs` parameter is a base64 protobuf. fast-flights' schema omits the per-leg
"selected flights" field (FlightData field 4), so we encode the query by hand:

  Info        { 3: FlightData (repeated), 8: Passenger (repeated: 1 adult, 2 child, 4 infant on lap),
                9: Seat (1=economy), 19: Trip (1=RT, 2=OW) }
  FlightData  { 2: date, 4: Segment (repeated, selected flights), 13: Airport from, 14: Airport to }
  Segment     { 1: from IATA, 2: date, 3: to IATA, 5: carrier, 6: flight number }
  Airport     { 2: IATA }

One-way  -> /travel/flights/booking : "Selected flights" + "Book with <airline> / OTAs" for that exact itinerary.
Round-trip, outbound only -> /travel/flights/search : outbound locked, Google asks to "Choose return".
Round-trip, both legs picked (separate legs / bundles) -> /travel/flights/booking for that exact pair.
Falls back to the fare's plain `search_url` when flight numbers are missing.
"""
import base64
import json
import re

BASE = "https://www.google.com/travel/flights"
FALLBACK = f"{BASE}?hl=en&curr=USD"
_FN = re.compile(r"^([A-Z0-9]{2})\s*(\d{1,4}[A-Z]?)$")


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num, value):
    if isinstance(value, int):
        return _varint(num << 3) + _varint(value)
    if isinstance(value, str):
        value = value.encode()
    return _varint(num << 3 | 2) + _varint(len(value)) + value


def split_flight_number(fn):
    """'DL1587' / 'DL 1587' -> ('DL', '1587'); None if it doesn't look like a flight number."""
    m = _FN.match((fn or "").strip().upper())
    return (m.group(1), m.group(2)) if m else None


def segments(fare):
    """[{from, to, date, flight}] for the outbound itinerary.

    Uses the stored per-leg `segments` when the source gave them; otherwise rebuilds them from
    flight_numbers + via_airports, assuming every leg departs on depart_date (true for most
    same-day connections; overnight ones may land on Google's search page instead).
    """
    stored = fare.get("segments")
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except ValueError:
            stored = None
    if stored:
        return stored
    numbers = [n for n in (fare.get("flight_numbers") or "").split(",") if n]
    via = [v for v in (fare.get("via_airports") or "").split(",") if v]
    stops = [fare.get("origin") or "TPA", *via, fare["destination"]]
    if not numbers or len(stops) != len(numbers) + 1:
        return []
    return [{"from": stops[i], "to": stops[i + 1], "date": fare["depart_date"], "flight": n}
            for i, n in enumerate(numbers)]


def _segment(s):
    parts = split_flight_number(s.get("flight"))
    if not parts:
        return None
    carrier, number = parts
    return (_field(1, s["from"]) + _field(2, s["date"]) + _field(3, s["to"])
            + _field(5, carrier) + _field(6, number))


def _leg(origin, dest, date, segs=()):
    body = _field(2, date) + b"".join(_field(4, s) for s in segs)
    return _field(3, body + _field(13, _field(2, origin)) + _field(14, _field(2, dest)))


PAX_ADULT, PAX_CHILD, PAX_LAP_INFANT = 1, 2, 4


def _passengers(party):
    from core.pricing import Party

    p = Party.coerce(party)
    codes = [PAX_ADULT] * p.adults + [PAX_CHILD] * p.children + [PAX_LAP_INFANT] * p.infants
    return b"".join(_field(8, c) for c in codes)


def _encoded_segments(fare):
    segs = [_segment(s) for s in segments(fare)]
    if not segs or any(s is None for s in segs):
        return None
    return segs


def encode(fare, party=1, return_fare=None):
    """tfs for this fare (outbound), optionally with the chosen return leg; None if flights unknown."""
    out = _encoded_segments(fare)
    if not out:
        return None
    origin, dest = fare.get("origin") or "TPA", fare["destination"]
    msg = _leg(origin, dest, fare["depart_date"], out)
    round_trip = bool(fare.get("return_date"))
    if round_trip:
        back = _encoded_segments(return_fare) if return_fare else []
        if return_fare and not back:
            return None
        msg += _leg(dest, origin, fare["return_date"], back)
    msg += _passengers(party) + _field(9, 1) + _field(19, 1 if round_trip else 2)
    return base64.urlsafe_b64encode(msg).decode().rstrip("=")


def book_url(fare, party=None, return_fare=None):
    """Link for Book now: the exact fare (and return, if chosen) when possible, else the route search."""
    party = party or fare.get("party") or fare.get("travelers") or 1
    tfs = encode(fare, party, return_fare)
    if not tfs:
        return fare.get("search_url") or FALLBACK
    page = "search" if fare.get("return_date") and not return_fare else "booking"
    return f"{BASE}/{page}?tfs={tfs}&hl=en&curr=USD"
