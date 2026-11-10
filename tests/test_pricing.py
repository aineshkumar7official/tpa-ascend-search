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
    assert off.bags_line() == "Personal item + carry-on included"       # never a separate "total with bags" (V6 p15)
    on = card_price(f, 0, 0, 1, True, POL)
    assert on.headline == 135 and on.is_estimate and on.bags_line() == "Price includes 1 carry-on + 1 checked"
    unknown = card_price({**f, "airline_iata": "ZZ"}, 1, 0, 1, True, POL)
    assert unknown.headline == 100 and not unknown.included
    assert unknown.bags_line() == "Bag info unavailable"


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
    assert cp.with_bags is None and cp.bags_line() == "Checked bag not included"
    assert cp.tooltip() == ""


# ---- V6 p15: the five bag states
V6_POL = {"XX": {"carry_on": {"fee_usd": 0}, "first_checked": {"fee_usd": 35}, "seat_selection": {"fee_usd": 18},
                 "extra_legroom": {"fee_usd": 45}},
          "IN": {"carry_on": {"fee_usd": 0}, "first_checked": {"fee_usd": 0}, "seat_selection": {"fee_usd": 18},
                 "extra_legroom": {"fee_usd": 45}},
          "RG": {"first_checked": {"fee_usd": None, "fee_label": "$55–$99"}, "seat_selection": {"fee_label": "Requires fee"}},
          "NO": {}}


def _v6_rows(code, include=False):
    from core.pricing import upgrade_rows

    f = {"price_usd": 159, "airline_iata": code, "trip_type": "one_way"}
    cp = card_price(f, 0, 0, 1, include, V6_POL)
    return cp, {r["id"]: r for r in upgrade_rows(f, cp, 1, V6_POL)}


def test_state_1_and_2_not_included_then_ticked():
    from core.pricing import upgrades_added

    cp, rows = _v6_rows("XX")
    assert cp.bags_line() == "Personal item + carry-on included" and cp.headline == 159
    assert (rows["checked"]["label"], rows["checked"]["fee"], rows["checked"]["included"]) == ("Add checked bag", 35, False)
    assert upgrades_added(rows.values(), {"checked"}) == 35 and cp.bags_line(checked_added=True) == "1 checked bag added"


def test_state_3_and_4_fare_covers_the_bag():
    from core.pricing import upgrades_added

    cp, rows = _v6_rows("IN")
    assert cp.bags_line() == "Carry-on + checked bag included"
    assert rows["checked"]["included"] and rows["checked"]["label"] == "Checked bag" and rows["checked"]["fee"] is None
    assert upgrades_added(rows.values(), {"checked", "seat_selection", "extra_legroom"}) == 63   # the bag can't add again


def test_home_toggle_counts_as_included():
    cp, rows = _v6_rows("XX", include=True)
    assert cp.headline == 194 and cp.bags_line() == "Price includes 1 carry-on + 1 checked" and rows["checked"]["included"]


def test_state_5_no_bag_data():
    from core.pricing import CHECK_GOOGLE, upgrades_added

    cp, rows = _v6_rows("NO")
    assert cp.bags_line() == "Bag info unavailable"
    assert all(r["note"] == CHECK_GOOGLE and r["fee"] is None for r in rows.values())
    assert rows["checked"]["label"] == "Checked bag" and upgrades_added(rows.values(), set(rows)) == 0


def test_ranges_stay_informative_but_cant_be_ticked():
    from core.pricing import CHECK_GOOGLE

    cp, rows = _v6_rows("RG")
    assert cp.bags_line() == "Checked bag not included" and rows["checked"]["note"] == "$55–$99" and rows["checked"]["fee"] is None
    assert rows["seat_selection"]["note"] == CHECK_GOOGLE      # "Requires fee" says nothing a traveler can act on


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
        {"fare_id": "5", "destination": "BOS", "price_usd": 60, "airline_iata": "YY", "trip_type": "one_way"},  # 60+50+40=150
    ]
    out = cheapest_with_bags(fares, 0, 0, 1, 3, pol)
    # XX to ATL beats cheaper-fare YY; 4 repeats XX and 1 repeats ATL; ZZ's fees are unknown.
    assert [f["fare_id"] for f, _ in out] == ["2", "5"]
    assert [cp.headline for _, cp in out] == [115, 150] and all(cp.included for _, cp in out)


# ---- bags picked: hide fares with unknown fees, add the fee to the price
def test_one_bag_two_travelers_adds_one_fee_to_scaled_fare():
    q = quote({"price_usd": 100, "airline_iata": "YY", "trip_type": "one_way"}, 1, 0, Party(2), POL)
    assert q.fare_total == 200 and q.bags_total == 50 and q.total == 250 and q.per_traveler == 125


def test_leg_totals_add_fees_and_leave_out_unknown():
    from core.pricing import leg_totals
    fares = [{"fare_id": "a", "price_usd": 300, "airline_iata": "XX"},
             {"fare_id": "b", "price_usd": 200, "airline_iata": "ZZ"}]
    assert leg_totals(fares, 0, 1, 2, policies=POL) == {"a": 370}
    assert leg_totals(fares, 0, 0, 2, policies=POL) == {"a": 300, "b": 200}      # no bags: nothing hidden
    ret = [{"fare_id": "r", "price_usd": 300, "airline_iata": "YY"}]
    assert leg_totals(ret, 0, 1, 2, out=fares[0], policies=POL) == {"r": 375}    # mixed airlines: 35 + 40
    assert leg_totals(ret, 0, 1, 2, out=fares[1], policies=POL) == {}


def test_bundles_with_bags_reprices_and_leaves_out_unknown():
    from core.pricing import bundles_with_bags
    xx, zz = {"airline_iata": "XX"}, {"airline_iata": "ZZ"}
    out = bundles_with_bags([{"out": xx, "ret": xx, "total": 300}, {"out": zz, "ret": zz, "total": 100}],
                            0, 1, 2, POL)
    assert [(b["total"], b["fare_total"]) for b in out] == [(370, 300)]


@pytest.mark.parametrize("policy,tag,level", [
    ({"personal_item": {"fee_usd": 0}, "carry_on": {"fee_usd": 0}, "first_checked": {"fee_usd": 0}},
     "Carry-on + checked bag included", "checked"),
    ({"personal_item": {"fee_usd": 0}, "carry_on": {"fee_usd": None}, "first_checked": {"fee_usd": 0}},
     "Checked bag included", "checked"),
    ({"personal_item": {"fee_usd": 0}, "carry_on": {"fee_usd": 0}, "first_checked": {"fee_usd": 45}},
     "Personal item + carry-on included", "carry"),
    ({"personal_item": {"fee_usd": 0}, "carry_on": {"fee_usd": 35}, "first_checked": {"fee_label": "$36–$50"}},
     "Personal item only", "personal"),
    ({"personal_item": {"fee_usd": 10}, "carry_on": {"fee_usd": 35}, "first_checked": {"fee_usd": 40}},
     "No bags included", "none"),
    ({}, "Bag info unavailable", "unknown"),
])
def test_bag_tag_names_which_bags_the_fare_includes(policy, tag, level):
    cp = card_price({"price_usd": 100, "airline_iata": "QQ", "trip_type": "one_way"}, 0, 0, 1, False, {"QQ": policy})
    assert cp.bags_line() == tag and cp.bag_level == level
