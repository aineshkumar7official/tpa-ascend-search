import json

from tests.conftest import FIXTURES
from sources import flights_fast, flights_serpapi


def test_fast_flights_oneway():
    payload = json.loads((FIXTURES / "fast_flights_tpa_atl_oneway.json").read_text())
    rows = flights_fast.normalize(payload, "TPA", "ATL", "2026-11-24", search_url="u")
    assert len(rows) == 19
    first = rows[0]
    assert first == {
        "origin": "TPA", "destination": "ATL", "trip_type": "one_way",
        "depart_date": "2026-11-24", "return_date": None, "stops": 0, "price_usd": 72.0,
        "airline_iata": "WN", "airline_name": "Southwest", "flight_numbers": "WN4214",
        "aircraft_type": "Boeing 737 MAX 8", "depart_time": "07:30", "arrive_time": "09:00",
        "duration_min": 90, "via_airports": None, "search_url": "u", "source": "fast_flights",
        "segments": [{"from": "TPA", "to": "ATL", "date": "2026-11-24", "flight": "WN4214"}],
    }
    assert all(r["stops"] == 0 for r in rows)
    assert len({(r["flight_numbers"], r["price_usd"]) for r in rows}) == len(rows)  # top/other deduped


def test_fast_flights_roundtrip():
    payload = json.loads((FIXTURES / "fast_flights_tpa_atl_roundtrip.json").read_text())
    rows = flights_fast.normalize(payload, "TPA", "ATL", "2026-11-24", "2026-12-01")
    assert rows[0]["trip_type"] == "round_trip"
    assert rows[0]["return_date"] == "2026-12-01"
    assert rows[0]["flight_numbers"] == "F92723" and rows[0]["price_usd"] == 109.0


def test_fast_flights_empty():
    assert flights_fast.normalize(None, "TPA", "ATL", "2026-11-24") == []


def test_clean_aircraft():
    assert flights_fast.clean_aircraft("Boeing 737MAX 8 Passenger") == "Boeing 737 MAX 8"
    assert flights_fast.clean_aircraft(None) is None


def test_serpapi():
    data = json.loads((FIXTURES / "serpapi_tpa_jfk_oneway.json").read_text())
    rows = flights_serpapi.normalize(data, "TPA", "JFK", "2026-11-13")
    assert len(rows) == 2
    b6, dl = rows
    assert b6["airline_iata"] == "B6" and b6["stops"] == 0 and b6["price_usd"] == 129.0
    assert b6["flight_numbers"] == "B61234" and b6["depart_time"] == "06:05" and b6["arrive_time"] == "08:52"
    assert b6["aircraft_type"] == "Airbus A321neo" and b6["booking_token"] == "tok_b6"
    assert dl["stops"] == 1 and dl["flight_numbers"] == "DL100,DL200" and dl["duration_min"] == 285
    assert dl["source"] == "serpapi"


def test_booking_options_parse():
    data = {"booking_options": [{"together": {"book_with": "JetBlue", "price": 129,
                                              "booking_request": {"url": "https://x/clk", "post_data": "a=1"}}}]}
    assert flights_serpapi.parse_booking_options(data) == [
        {"book_with": "JetBlue", "price": 129, "url": "https://x/clk?a=1"}]
