from core import queries

NOW = "2026-11-02T12:00:00+00:00"


def _fare(conn, dest, airline, price, trip="one_way"):
    conn.execute("""INSERT INTO fares(scan_id, scanned_at, destination, trip_type, window_id, scan_mode, depart_date,
                    stops, price_usd, airline_iata, source, status) VALUES ('s1',?,?,?,'wkend+2','nonstop',
                    '2026-11-13',0,?,?,'fast_flights','ready_to_publish')""", (NOW, dest, trip, price, airline))
    conn.commit()


def _picks(conn):
    return [(f["airline_iata"], f["destination"]) for f in queries.cheapest_mix(conn, "one_way", 3)]


def test_three_airlines_to_three_cities(conn):
    for dest, airline, price in [("ATL", "F9", 19), ("DFW", "F9", 25), ("ATL", "WN", 59), ("ATL", "DL", 69),
                                 ("BNA", "WN", 79), ("MSP", "SY", 109), ("LAX", "UA", 119)]:
        _fare(conn, dest, airline, price)
    assert _picks(conn) == [("F9", "ATL"), ("WN", "BNA"), ("SY", "MSP")]  # DL only flies to ATL here


def test_airports_in_one_metro_count_as_one_city(conn):
    for dest, airline, price in [("JFK", "B6", 50), ("LGA", "DL", 60), ("BOS", "AA", 70)]:
        _fare(conn, dest, airline, price)
    assert _picks(conn) == [("B6", "JFK"), ("AA", "BOS")]


def test_fewer_cards_rather_than_a_repeat_and_unknown_airline_skipped(conn):
    _fare(conn, "ATL", "F9", 19)
    _fare(conn, "DFW", "F9", 25)
    _fare(conn, "BOS", None, 5)
    assert _picks(conn) == [("F9", "ATL")]
