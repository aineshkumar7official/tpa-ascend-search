"""Experience score (0–10) for flights and round-trip bundles.

Transparent and data-only — nothing is guessed:
  Comfort  0–4  verified amenities (Wi-Fi 1, seatback screen 1, streaming 0.5, power 0.5) + legroom (≤1)
  Reviews  0–3  passenger review stars (★/5 × 3)
  Time     0–3  shortest option in the set gets 3; −0.5 per extra 30 min
Unknown inputs (amenity not verified, no reviews) get HALF credit so missing data neither rewards
nor punishes an airline; `complete` is False when any input was unknown so the UI can say so.
"""
from dataclasses import dataclass, field

AMENITY_POINTS = {"wifi": 1.0, "seatback_screen": 1.0, "stream_to_device": 0.5, "power": 0.5}
EXPLAINER = ("Experience score: comfort (verified Wi-Fi, screens, power, legroom) up to 4, passenger "
             "reviews up to 3, flight time up to 3. Unverified items count half.")


def _pitch(value):
    """'30–31' -> 30.5; '32' -> 32.0; None if unknown."""
    if not value:
        return None
    nums = [float(x) for x in str(value).replace("–", "-").split("-") if x.strip().replace(".", "").isdigit()]
    return sum(nums) / len(nums) if nums else None


def _legroom_points(pitch):
    if pitch is None:
        return 0.5, False
    if pitch >= 32:
        return 1.0, True
    if pitch >= 31:
        return 0.75, True
    if pitch >= 30:
        return 0.5, True
    return 0.25, True


@dataclass
class Score:
    total: float
    comfort: float
    reviews: float
    time: float
    complete: bool
    unknown: list = field(default_factory=list)


def flight_score(fare, shortest_min):
    amen = fare.get("amenities") or {}
    unknown = []
    comfort = 0.0
    for key, pts in AMENITY_POINTS.items():
        v = amen.get(key)
        if v is True:
            comfort += pts
        elif v is None:
            comfort += pts / 2
            unknown.append(key)
    legroom, known = _legroom_points(_pitch(amen.get("legroom_pitch_in")))
    comfort += legroom
    if not known:
        unknown.append("legroom")
    review = fare.get("review") or {}
    if review.get("stars_5") is not None and review.get("review_count"):
        reviews = review["stars_5"] / 5 * 3
    else:
        reviews = 1.5
        unknown.append("reviews")
    extra = max(0, (fare.get("duration_min") or shortest_min or 0) - (shortest_min or 0))
    time = max(0.0, 3 - 0.5 * (extra / 30))
    total = round(min(10.0, comfort + reviews + time), 1)
    return Score(total, round(comfort, 2), round(reviews, 2), round(time, 2), not unknown, unknown)


def bundle_score(out, ret, shortest_out, shortest_ret):
    a, b = flight_score(out, shortest_out), flight_score(ret, shortest_ret)
    return Score(round((a.total + b.total) / 2, 1), round((a.comfort + b.comfort) / 2, 2),
                 round((a.reviews + b.reviews) / 2, 2), round((a.time + b.time) / 2, 2),
                 a.complete and b.complete, sorted(set(a.unknown) | set(b.unknown)))


def same_aircraft(out, ret):
    return bool(out.get("aircraft_type")) and out.get("aircraft_type") == ret.get("aircraft_type")


def rank_bundles(bundles, allow_mixed=False):
    """Score, filter (same airline unless allowed) and tag Best experience / Lowest price / Shortest."""
    pool = [b for b in bundles if allow_mixed or b["out"].get("airline_iata") == b["ret"].get("airline_iata")]
    if not pool:
        return []
    s_out = min((b["out"].get("duration_min") or 0) for b in pool)
    s_ret = min((b["ret"].get("duration_min") or 0) for b in pool)
    for b in pool:
        b["score"] = bundle_score(b["out"], b["ret"], s_out, s_ret)
        b["duration"] = (b["out"].get("duration_min") or 0) + (b["ret"].get("duration_min") or 0)
        b["tags"] = []
    best = max(pool, key=lambda b: (b["score"].total, -b["total"]))
    cheap = min(pool, key=lambda b: (b["total"], -b["score"].total))
    short = min(pool, key=lambda b: (b["duration"], b["total"]))
    best["tags"].append("Best experience")
    cheap["tags"].append("Lowest price")
    short["tags"].append("Shortest travel time")
    return pool


SORTS = {
    "Best experience": lambda b: (-b["score"].total, b["total"]),
    "Lowest price": lambda b: (b["total"], -b["score"].total),
    "Shortest": lambda b: (b["duration"], b["total"]),
}
