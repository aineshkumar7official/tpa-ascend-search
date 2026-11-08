"""Reading Google's fare options, and using them for the card price and bag fees. Page text is as Google renders it."""
from datetime import datetime, timedelta, timezone

from core.db import cache_set
from core.pricing import card_price, google_policies, upgrades
from sources import fare_options as fo

UNITED = """Selected flights
Booking options
Book with United
Airline
from
$160
Hide options
Basic Economy
$160
Seat selection for a fee
Standard seat
Last to board
Ticket changes for a fee
No refunds
No carry-on bags
First checked bag costs 50 US dollars
1st checked bag: $50
Continue
Economy
$220
Free seat selection
Extra legroom available for a fee
Free change, possible fare difference
No refunds
1 free carry-on
First checked bag costs 50 US dollars
1st checked bag: $50
Continue
Economy Fully Refundable
$1,260
Free seat selection
Full refunds
1 free carry-on
1st checked bag free
Continue
Fare and baggage fees apply to your entire trip.
Book with FlightHub
$95
Continue
Prices include required taxes + fees for 1 adult."""

ONE_PRICE = """Booking options
How options are ranked
Book with Sun Country Airlines
Airline
$149
Continue
View options
Book with Ovago
$157
Continue
View options
Prices include required taxes + fees for 1 adult."""

AGENCIES_ONLY = """Booking options
Book with FlightHub
$95
Continue
Prices include required taxes + fees for 1 adult."""

POL = {"UA": {"carry_on": {"fee_usd": None, "each_way": True}, "first_checked": {"fee_usd": 45, "each_way": True},
              "seat_selection": {"fee_usd": None}, "extra_legroom": {"fee_usd": None}},
       "DL": {"carry_on": {"fee_usd": 0, "each_way": True}, "first_checked": {"fee_usd": 45, "each_way": True},
              "seat_selection": {"fee_usd": None}, "extra_legroom": {"fee_usd": None}}}


def test_reads_each_airline_fare_cheapest_first():
    data = fo.parse(UNITED)
    assert data["airline"] == "United" and data["airline_price"] == 160
    assert [(o["name"], o["price"]) for o in data["options"]] == [
        ("Basic Economy", 160), ("Economy", 220), ("Economy Fully Refundable", 1260)]


def test_reads_bag_rules_and_drops_duplicate_wording():
    basic, economy, refundable = fo.parse(UNITED)["options"]
    assert (basic["first_bag"], basic["carry_on"]) == (50, "none")
    assert (economy["first_bag"], economy["carry_on"]) == (50, "free")
    assert refundable["first_bag"] == 0
    assert "1st checked bag $50" in basic["lines"]
    assert not any(ln.startswith("First checked bag costs") or ln == "Continue" for ln in basic["lines"])


def test_agency_rows_are_not_read_as_fares():
    assert all(o["name"] != "Book with FlightHub" for o in fo.parse(UNITED)["options"])
    assert fo.parse(AGENCIES_ONLY) == {"airline": None, "airline_price": None, "options": []}


def test_party_wording_for_the_bag_fee():
    text = UNITED.replace("1st checked bag: $50", "1st checked bag per passenger: $50")
    assert fo.parse(text)["options"][0]["first_bag"] == 50


def test_airline_with_one_price_and_no_list():
    data = fo.parse(ONE_PRICE)
    assert data["airline"] == "Sun Country Airlines" and data["airline_price"] == 149 and data["options"] == []
    assert fo.cheapest(data) is None and fo.upgrades(data) == []


def test_upgrades_show_only_what_changes():
    ups = fo.upgrades(fo.parse(UNITED))
    assert (ups[0]["name"], ups[0]["extra"]) == ("Economy", 60)
    assert "1 free carry-on" in ups[0]["changes"] and "No refunds" not in ups[0]["changes"]


def _fare(trip="one_way", price=170.0):
    return {"airline_iata": "UA", "price_usd": price, "trip_type": trip, "travelers": 1, "destination": "DEN",
            "depart_date": "2026-12-12", "flight_numbers": "UA2424"}


def test_card_shows_google_price_not_the_scanned_one():
    cp = card_price(_fare(), policies=POL, google=fo.parse(UNITED))
    assert cp.headline == 160 and not cp.is_estimate


def test_scanned_price_stays_without_google():
    assert card_price(_fare(), policies=POL).headline == 170
    assert card_price(_fare(), policies=POL, google=fo.parse(AGENCIES_ONLY)).headline == 170


def test_google_price_is_the_party_total_not_scaled():
    assert card_price(_fare(), party=2, policies=POL, google=fo.parse(UNITED)).headline == 160


def test_round_trip_bag_fee_from_google_is_not_doubled():
    data = fo.parse(UNITED.replace("1st checked bag: $50", "1st checked bag: $100"))
    cp = card_price(_fare("round_trip"), carry_on=0, checked=1, policies=POL, google=data)
    assert cp.with_bags == 160 + 100
    assert card_price(_fare("round_trip"), carry_on=0, checked=1, policies=POL).with_bags == 170 + 90  # airline-wide, each way


def test_fare_without_a_carry_on_has_no_with_bags_total():
    assert card_price(_fare(), carry_on=1, checked=0, policies=POL, google=fo.parse(UNITED)).with_bags is None


def test_upgrade_menu_uses_this_fares_rules():
    data = fo.parse(UNITED.replace("Seat selection for a fee", "No seat selection"))
    ups = {u["label"]: u for u in upgrades(_fare(), 160, 1, google_policies("UA", data, POL))}
    assert ups["Add checked bag"]["fee"] == 50
    assert ups["Choose seat"]["fee_label"] == "Not on this fare"


def test_google_policies_leave_other_airlines_and_empty_answers_alone():
    merged = google_policies("UA", fo.parse(UNITED), POL)
    assert merged["DL"] is POL["DL"] and POL["UA"]["first_checked"]["fee_usd"] == 45
    assert google_policies("UA", fo.parse(ONE_PRICE), POL) is POL


def test_round_trip_needs_its_return_flight():
    segs = [{"from": "TPA", "to": "DEN", "date": "2026-12-12", "flight": "UA2424"}]
    out = {**_fare("round_trip"), "return_date": "2026-12-19", "segments": segs, "origin": "TPA"}
    back = {"segments": [{"from": "DEN", "to": "TPA", "date": "2026-12-19", "flight": "UA100"}]}
    assert not fo.lookable(out) and fo.lookable(out, back)


def test_cache_key_separates_party_and_return():
    segs = [{"from": "TPA", "to": "DEN", "date": "2026-12-12", "flight": "UA2424"}]
    f = {**_fare(), "segments": segs}
    back = {"segments": [{"from": "DEN", "to": "TPA", "date": "2026-12-19", "flight": "UA100"}]}
    assert len({fo.cache_key(f, 1), fo.cache_key(f, 2), fo.cache_key(f, 1, back)}) == 3


def test_cached_answers_expire(conn):
    f = {**_fare(), "segments": [{"from": "TPA", "to": "DEN", "date": "2026-12-12", "flight": "UA2424"}]}
    key = fo.cache_key(f, 1)
    cache_set(conn, key, fo.parse(UNITED))

    def age(**delta):
        at = (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()
        conn.execute("UPDATE http_cache SET fetched_at=? WHERE cache_key=?", (at, key))

    age(hours=5)
    assert fo.cached(conn, f, 1)[0]
    age(hours=7)
    assert not fo.cached(conn, f, 1)[0]
    cache_set(conn, key, {"options": [], "error": "timeout"})
    age(minutes=30)
    assert fo.cached(conn, f, 1)[0]
    age(minutes=90)
    assert not fo.cached(conn, f, 1)[0]


def test_lookup_is_skipped_when_turned_off(conn):
    assert not fo.available() and fo.lookup(conn, _fare(), 1) is None
