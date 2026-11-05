import base64
import json

from fast_flights.pb.flights_pb2 import Info

from core.booking import book_url, encode, segments, split_flight_number

DL = {"origin": "TPA", "destination": "ATL", "depart_date": "2026-12-01", "flight_numbers": "DL1587",
      "search_url": "https://fallback"}
# Verified in Chrome on 2026-11-02: opens "Selected flights · DL 12:20 PM · Book with Delta · $89".
GOLDEN = "GjwSCjIwMjYtMTItMDEiIAoDVFBBEgoyMDI2LTEyLTAxGgNBVEwqAkRMMgQxNTg3agUSA1RQQXIFEgNBVExAAUgBmAEC"


def _info(tfs):
    return Info.FromString(base64.urlsafe_b64decode(tfs + "=" * (-len(tfs) % 4)))


def test_golden_one_way_link():
    assert encode(DL) == GOLDEN
    assert book_url(DL) == f"https://www.google.com/travel/flights/booking?tfs={GOLDEN}&hl=en&curr=USD"


def test_round_trip_locks_outbound_on_search_page():
    url = book_url({**DL, "return_date": "2026-12-04"}, party=3)
    assert url.startswith("https://www.google.com/travel/flights/search?tfs=")
    info = _info(url.split("tfs=")[1].split("&")[0])
    assert info.trip == 1 and len(info.passengers) == 3
    assert [(d.date, d.from_airport.airport, d.to_airport.airport) for d in info.data] == [
        ("2026-12-01", "TPA", "ATL"), ("2026-12-04", "ATL", "TPA")]


def test_one_stop_segments_from_via_airports():
    f = {"destination": "ATL", "depart_date": "2026-11-20", "flight_numbers": "WN575,WN226", "via_airports": "IND"}
    assert segments(f) == [{"from": "TPA", "to": "IND", "date": "2026-11-20", "flight": "WN575"},
                           {"from": "IND", "to": "ATL", "date": "2026-11-20", "flight": "WN226"}]
    raw = base64.urlsafe_b64decode(encode(f) + "==")
    assert b"WN" in raw and b"575" in raw and b"226" in raw


def test_stored_segments_win_overnight_dates():
    f = {**DL, "flight_numbers": "F92684,F92409", "via_airports": "CLE",
         "segments": json.dumps([{"from": "TPA", "to": "CLE", "date": "2026-12-01", "flight": "F92684"},
                                 {"from": "CLE", "to": "ATL", "date": "2026-12-02", "flight": "F92409"}])}
    assert segments(f)[1]["date"] == "2026-12-02"


def test_fallback_without_flight_numbers():
    assert book_url({**DL, "flight_numbers": None}) == "https://fallback"
    assert book_url({**DL, "flight_numbers": "DL1,DL2"}) == "https://fallback"   # 2 flights but no via airport
    assert split_flight_number("B6 1234") == ("B6", "1234") and split_flight_number("??") is None
