import pytest

from core.pricing import Party, bag_fees, bag_limits, quote, rt_quote

POL = {
    "XX": {"carry_on": {"fee_usd": 0, "each_way": True}, "first_checked": {"fee_usd": 35, "each_way": True}},
    "YY": {"carry_on": {"fee_usd": 50, "each_way": True}, "first_checked": {"fee_usd": 40, "each_way": False}},
    "ZZ": {"carry_on": {"fee_usd": None}, "first_checked": {"fee_usd": None}},
}


# Bags are TOTALS for the trip (wireframes V2), not per traveler.
@pytest.mark.parametrize("airline,carry,checked,trip,expected", [
    ("XX", 0, 0, "one_way", 0),
    ("XX", 1, 1, "one_way", 35),
    ("XX", 2, 2, "round_trip", 140),     # 2 bags x $35 x 2 directions
    ("YY", 1, 0, "round_trip", 100),     # carry-on fee doubles each way
    ("YY", 0, 3, "round_trip", 120),     # not each_way -> no doubling
    ("YY", 0, 2, "one_way", 80),
])
def test_bag_fees_trip_totals(airline, carry, checked, trip, expected):
    assert bag_fees(airline, carry, checked, trip, POL) == expected


def test_unknown_fee_returns_fare_only_with_note():
    q = quote({"price_usd": 120, "airline_iata": "ZZ", "trip_type": "one_way"}, 1, 0, 1, POL)
    assert q.total == 120 and q.bags_total is None and not q.is_estimate
    assert "Bag fees not included" in q.note
    assert q.bags_chip().startswith("Bags not included")


def test_bag_total_is_estimate_with_breakdown_and_chip():
    q = quote({"price_usd": 100, "airline_iata": "XX", "trip_type": "one_way"}, 1, 1, 1, POL)
    assert q.total == 135 and q.is_estimate
    assert q.breakdown() == "Fare $100 + bags ~$35"
    assert q.bags_chip() == "Price includes 1 carry-on + 1 checked"
    assert quote({"price_usd": 100, "airline_iata": "XX"}, 0, 0, 1, POL).bags_chip() == "Bags not included"


def test_party_scaling_and_per_traveler():
    q = quote({"price_usd": 100, "airline_iata": "XX", "trip_type": "one_way"}, 0, 0, Party(2, 1, 0), POL)
    assert q.total == 300 and q.per_traveler == 100      # 1-adult background fare scaled to 3
    live = quote({"price_usd": 290, "travelers": 3, "airline_iata": "XX", "trip_type": "one_way"}, 0, 0, 3, POL)
    assert live.total == 290                              # live fare already priced for the party


def test_party_labels_and_limits():
    assert Party(1).label() == "1 adult"
    assert Party(2, 1).label() == "2 adults, 1 child"
    assert Party(2, 2, 1).label() == "2 adults, 2 children, 1 infant"
    p = Party(2, 0, 2)
    assert p.limits()["adults"][0] == 2          # can't drop below infants (one lap each)
    assert p.limits()["infants"][1] == 2         # infants capped at adults
    assert Party(5, 4, 0).limits()["children"][1] == 4   # total capped at 9
    assert bag_limits(Party(2, 1, 1)) == {"carry_on": (0, 3), "checked": (0, 9)}  # lap infants get no seat/bag
    assert Party.coerce({"adults": 2, "children": 1}) == Party(2, 1, 0) and Party.coerce(3) == Party(3)


def test_round_trip_quote_same_and_mixed_airlines():
    same = rt_quote({"airline_iata": "XX"}, {"airline_iata": "XX"}, 300, 0, 1, Party(2), POL)
    assert same.total == 370 and same.items == {"carry_on": 0.0, "checked": 70.0}
    mixed = rt_quote({"airline_iata": "XX"}, {"airline_iata": "YY"}, 300, 0, 1, 2, POL)
    assert mixed.items["checked"] == 75.0         # one-way fee per leg: 35 + 40
    unknown = rt_quote({"airline_iata": "XX"}, {"airline_iata": "ZZ"}, 300, 1, 0, 1, POL)
    assert unknown.bags_total is None and unknown.total == 300


# ---- V3 card pricing + upgrades
from core.pricing import card_price, upgrades  # noqa: E402


def test_card_price_bags_line_and_toggle():
    f = {"price_usd": 100, "airline_iata": "XX", "trip_type": "one_way"}
    off = card_price(f, 0, 0, 1, False, POL)            # no bags picked -> 1 carry-on + 1 checked reference
    assert off.headline == 100 and off.with_bags == 135
    assert off.bags_line() == "Bags not included · $135 with bags"
    on = card_price(f, 0, 0, 1, True, POL)
    assert on.headline == 135 and on.is_estimate and on.bags_line() == "Bags included · 1 carry-on + 1 checked"
    unknown = card_price({**f, "airline_iata": "ZZ"}, 1, 0, 1, True, POL)
    assert unknown.headline == 100 and not unknown.included
    assert unknown.bags_line() == "Bags not included · bag fees not verified yet"


def test_upgrades_scale_and_unknowns():
    pol = {"XX": {**POL["XX"], "seat_selection": {"fee_usd": 20}, "extra_legroom": {"fee_usd": None}}}
    f = {"price_usd": 200, "airline_iata": "XX", "trip_type": "round_trip"}
    ups = {u["label"]: u for u in upgrades(f, 200, Party(2, 0, 1), pol)}
    assert ups["Add checked bag"]["fee"] == 70 and ups["Add checked bag"]["total"] == 270   # $35 each way
    assert ups["Choose seat"]["fee"] == 80                     # $20 × 2 seats × 2 flights (lap infant: no seat)
    assert ups["Extra legroom"]["fee"] is None and ups["Extra legroom"]["total"] is None


def test_bags_line_when_fees_apply_without_amount():
    pol = {"XX": {"first_checked": {"fee_usd": None, "fee_label": "Requires fee"}}}
    cp = card_price({"price_usd": 100, "airline_iata": "XX", "trip_type": "one_way"}, 0, 0, 1, False, pol)
    assert cp.with_bags is None and cp.bags_line() == "Bags not included"
    assert "verified" not in cp.tooltip()


def test_upgrades_fee_label_without_amount():
    pol = {"XX": {"first_checked": {"fee_usd": None, "fee_label": "Requires fee"}}}
    ups = {u["label"]: u for u in upgrades({"airline_iata": "XX", "trip_type": "one_way"}, 100, 1, pol)}
    assert ups["Add checked bag"]["fee"] is None and ups["Add checked bag"]["fee_label"] == "Requires fee"
    assert ups["Choose seat"]["fee_label"] is None  # unmarked stays "not verified"


def test_bags_included_reranks_by_total_and_drops_unknown_fees():
    from core.pricing import cheapest_with_bags
    pol = {"XX": POL["XX"], "YY": POL["YY"], "ZZ": POL["ZZ"]}
    fares = [
        {"fare_id": "1", "destination": "ATL", "price_usd": 40, "airline_iata": "YY", "trip_type": "one_way"},  # 40+50+40=130
        {"fare_id": "2", "destination": "ATL", "price_usd": 80, "airline_iata": "XX", "trip_type": "one_way"},  # 80+0+35=115
        {"fare_id": "3", "destination": "JFK", "price_usd": 10, "airline_iata": "ZZ", "trip_type": "one_way"},  # unknown fees
        {"fare_id": "4", "destination": "BOS", "price_usd": 95, "airline_iata": "XX", "trip_type": "one_way"},  # 130
    ]
    out = cheapest_with_bags(fares, 0, 0, 1, 3, pol)
    assert [f["fare_id"] for f, _ in out] == ["2", "4"]          # ATL via XX beats cheaper-fare YY; ZZ dropped
    assert [cp.headline for _, cp in out] == [115, 130] and all(cp.included for _, cp in out)
