"""Travelers + bag-fee math, applied at display time (never stored on fares).

Travelers are a Party (adults 12+, children 2–11, infants under 2 on a lap). Live searches price the
whole party; background fares are priced for 1 adult and scaled until a live search re-prices them.
Bags are counted as the TOTAL for the trip (wireframes V2), estimated from airline_policies.json
`fee_usd`. Unknown fees -> fare only + a note. Totals with bags are "est.".
"""
from dataclasses import dataclass

from core import config

MAX_TRAVELERS = 9  # Google Flights limit per search


@dataclass(frozen=True)
class Party:
    adults: int = 1
    children: int = 0
    infants: int = 0   # under 2, on a lap — must travel with an adult

    @classmethod
    def coerce(cls, value):
        """Party from a Party, an int (adults) or a dict with adults/children/infants."""
        if isinstance(value, Party):
            return value
        if isinstance(value, dict):
            return cls(int(value.get("adults") or 1), int(value.get("children") or 0), int(value.get("infants") or 0))
        return cls(adults=max(1, int(value or 1)))

    @property
    def size(self):
        return self.adults + self.children + self.infants

    @property
    def seats(self):
        return self.adults + self.children

    def as_dict(self):
        return {"adults": self.adults, "children": self.children, "infants": self.infants}

    def label(self):
        parts = [f"{self.adults} adult{'s' if self.adults != 1 else ''}"]
        if self.children:
            parts.append(f"{self.children} child{'ren' if self.children != 1 else ''}")
        if self.infants:
            parts.append(f"{self.infants} infant{'s' if self.infants != 1 else ''}")
        return ", ".join(parts)

    def limits(self):
        """Stepper (min, max) per field, given the other fields: total ≤ 9 and infants ≤ adults."""
        room = MAX_TRAVELERS - self.size
        return {"adults": (max(1, self.infants), self.adults + room),
                "children": (0, self.children + room),
                "infants": (0, min(self.adults, self.infants + room))}

    def valid(self):
        return self.adults >= 1 and self.infants <= self.adults and self.size <= MAX_TRAVELERS


def bag_limits(party):
    """Bags are trip totals: one carry-on per seated traveler, up to 3 checked bags each."""
    party = Party.coerce(party)
    return {"carry_on": (0, party.seats), "checked": (0, 3 * party.seats)}


def bags_text(carry_on, checked):
    parts = []
    if carry_on:
        parts.append(f"{carry_on} carry-on")
    if checked:
        parts.append(f"{checked} checked")
    return " + ".join(parts)


@dataclass
class Quote:
    fare_total: float          # price for the whole party, no bags
    bags_total: float | None   # estimated bag fees for the trip, None if unknown
    travelers: int             # party size
    carry_on: int = 0
    checked: int = 0
    note: str | None = None

    @property
    def has_bags(self):
        return bool(self.bags_total)

    @property
    def total(self):
        return self.fare_total + (self.bags_total or 0)

    @property
    def per_traveler(self):
        return self.total / max(self.travelers, 1)

    @property
    def is_estimate(self):
        return self.has_bags

    def breakdown(self):
        if not self.has_bags:
            return None
        return f"Fare ${self.fare_total:,.0f} + bags ~${self.bags_total:,.0f}"

    def bags_chip(self):
        """Card chip: what the shown price includes."""
        wanted = bags_text(self.carry_on, self.checked)
        if not wanted:
            return "Bags not included"
        if self.bags_total is None:
            return "Bags not included · fees not verified for this airline"
        return f"Price includes {wanted}"


def _fee(policy, key, trip_type):
    item = (policy or {}).get(key) or {}
    fee = item.get("fee_usd")
    if fee is None:
        return None
    mult = 2 if trip_type == "round_trip" and item.get("each_way") else 1
    return float(fee) * mult


def bag_fees(airline, carry_on, checked, trip_type, policies=None):
    """Estimated fees for `carry_on` + `checked` bags (trip totals), or None if a needed fee is unknown.

    2nd+ checked bags reuse the 1st-bag fee (a floor — airlines charge more for extra bags).
    """
    if not carry_on and not checked:
        return 0.0
    policy = (policies if policies is not None else config.policies()).get(airline or "")
    total = 0.0
    for count, key in ((carry_on, "carry_on"), (checked, "first_checked")):
        if count:
            fee = _fee(policy, key, trip_type)
            if fee is None:
                return None
            total += fee * count
    return total


def quote(fare, carry_on=0, checked=0, party=1, policies=None):
    """`fare['price_usd']` is the total for `fare['travelers']` (default 1) travelers."""
    party = Party.coerce(party)
    fare_total = float(fare["price_usd"])
    priced_for = int(fare.get("travelers") or 1)
    if priced_for != party.size:
        # Background fares are priced for 1 adult; scale until a live search re-prices them.
        fare_total = fare_total / priced_for * party.size
    bags = bag_fees(fare.get("airline_iata"), carry_on, checked, fare.get("trip_type"), policies)
    note = None
    if bags is None:
        note = f"Bag fees not included for {config.airline_name(fare.get('airline_iata'))}."
    return Quote(fare_total=fare_total, bags_total=bags, travelers=party.size,
                 carry_on=carry_on, checked=checked, note=note)


def bag_fee_items(airline, carry_on, checked, trip_type, policies=None):
    """{'carry_on': fee|None, 'checked': fee|None} for the breakdown rows (0 when none requested)."""
    policy = (policies if policies is not None else config.policies()).get(airline or "")
    return {"carry_on": _fee(policy, "carry_on", trip_type) * carry_on if carry_on and _fee(policy, "carry_on", trip_type) is not None
            else (0.0 if not carry_on else None),
            "checked": _fee(policy, "first_checked", trip_type) * checked if checked and _fee(policy, "first_checked", trip_type) is not None
            else (0.0 if not checked else None)}


@dataclass
class RoundTripQuote(Quote):
    items: dict | None = None   # per-bag-type fees for the breakdown


def rt_quote(out, ret, total_price, carry_on=0, checked=0, party=1, policies=None):
    """Quote for a chosen outbound + return. `total_price` is Google's round-trip total for the party.

    Same airline both ways: round-trip bag rules. Different airlines: each leg's one-way fees, summed.
    """
    party = Party.coerce(party)
    a, b = out.get("airline_iata"), ret.get("airline_iata")
    if a == b:
        items = bag_fee_items(a, carry_on, checked, "round_trip", policies)
    else:
        x = bag_fee_items(a, carry_on, checked, "one_way", policies)
        y = bag_fee_items(b, carry_on, checked, "one_way", policies)
        items = {k: (None if x[k] is None or y[k] is None else x[k] + y[k]) for k in x}
    bags = None if None in items.values() else sum(items.values())
    note = None if bags is not None else "Bag fees not verified for this airline — not included."
    return RoundTripQuote(fare_total=float(total_price), bags_total=bags, travelers=party.size,
                          carry_on=carry_on, checked=checked, note=note, items=items)


# ---------------------------------------------------------------- V3 card pricing + upgrades
DEFAULT_CARD_BAGS = (1, 1)  # carry-on, checked used for "[$Total] with bags" when none are picked


@dataclass
class CardPrice:
    """What a V3 fare card shows: headline price, the bags line and the base for Upgrades."""
    fare_total: float               # whole party, no bags
    with_bags: float | None         # fare + estimated fees for `bags` (None = fees unknown)
    bags: tuple                     # (carry_on, checked) the with-bags total is for
    included: bool                  # headline includes those bags
    travelers: int
    fees_apply: bool = False        # airline charges for bags, amount unknown (policy fee_label)

    @property
    def headline(self):
        return self.with_bags if self.included else self.fare_total

    @property
    def is_estimate(self):
        return self.included and self.with_bags != self.fare_total

    def bags_line(self, money=lambda v: f"${v:,.0f}"):
        what = bags_text(*self.bags)
        if self.included:
            return f"Bags included · {what}"
        if self.with_bags is None:
            return "Bags not included" if self.fees_apply else "Bags not included · bag fees not verified yet"
        return f"Bags not included · {money(self.with_bags)} with bags"

    def tooltip(self, money=lambda v: f"${v:,.0f}"):
        if self.with_bags is None:
            return ("Bags cost extra, so the price is fare only. See the booking page for bag prices." if self.fees_apply
                    else "Bag fees for this airline aren't verified yet, so the price is fare only.")
        return (f"Fare {money(self.fare_total)} + bags ~{money(self.with_bags - self.fare_total)} "
                f"for {bags_text(*self.bags)} (trip total, estimated)")


def card_price(fare, carry_on=0, checked=0, party=1, include_bags=False, policies=None):
    """Card price. The with-bags total uses the picked bags, or 1 carry-on + 1 checked when none are picked.
    `include_bags` puts that total in the headline (only when the fees are known)."""
    bags = (carry_on, checked) if (carry_on or checked) else DEFAULT_CARD_BAGS
    q = quote(fare, bags[0], bags[1], party, policies)
    with_bags = q.total if q.bags_total is not None else None
    policy = (policies if policies is not None else config.policies()).get(fare.get("airline_iata") or "") or {}
    return CardPrice(fare_total=q.fare_total, with_bags=with_bags, bags=bags,
                     included=bool(include_bags and with_bags is not None), travelers=q.travelers,
                     fees_apply=bool((policy.get("first_checked") or {}).get("fee_label")))


def extra_fee(airline, key, trip_type, party, policies=None):
    """Seat / extra-legroom fee for the trip: policy fee_usd × seated travelers × flights. None if unknown."""
    policy = (policies if policies is not None else config.policies()).get(airline or "") or {}
    fee = (policy.get(key) or {}).get("fee_usd")
    if fee is None:
        return None
    flights = 2 if trip_type == "round_trip" else 1
    return float(fee) * Party.coerce(party).seats * flights


UPGRADES = (("checked", "Add checked bag"), ("seat_selection", "Choose seat"), ("extra_legroom", "Extra legroom"))


def upgrades(fare, base_total, party=1, policies=None):
    """[{label, fee, total, fee_label}] for the card's Upgrades menu; fee/total None when the amount is unknown.
    fee_label is the policy's wording for a fee with no known amount (e.g. "Requires fee"), else None."""
    pols = policies if policies is not None else config.policies()
    airline, trip = fare.get("airline_iata"), fare.get("trip_type")
    policy = pols.get(airline or "") or {}
    out = []
    for key, label in UPGRADES:
        if key == "checked":
            fee = _fee(pols.get(airline or ""), "first_checked", trip)
        else:
            fee = extra_fee(airline, key, trip, party, pols)
        item = policy.get("first_checked" if key == "checked" else key) or {}
        out.append({"label": label, "fee": fee, "total": None if fee is None else base_total + fee,
                    "fee_label": item.get("fee_label")})
    return out


def cheapest_with_bags(fares, carry_on=0, checked=0, party=1, n=3, policies=None):
    """Home with 'Bags included' on: [(fare, CardPrice)] ranked by the with-bags total, one per destination.
    Fares whose bag fees aren't verified are left out (their bags-included price is unknown)."""
    priced = []
    for f in fares:
        cp = card_price(f, carry_on, checked, party, True, policies)
        if cp.included:
            priced.append((f, cp))
    priced.sort(key=lambda x: (x[1].headline, x[0].get("depart_date") or ""))
    out, seen = [], set()
    for f, cp in priced:
        if f["destination"] not in seen:
            seen.add(f["destination"])
            out.append((f, cp))
    return out[:n]
