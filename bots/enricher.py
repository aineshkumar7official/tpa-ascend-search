"""Bot 2 — Enricher: livery + cabin photos per (airline, aircraft type), cached in `assets`."""
import logging
import re
from datetime import datetime, timedelta, timezone

from core import config
from core.db import utcnow
from sources import commons, planespotters

log = logging.getLogger(__name__)

REFRESH_DAYS = 30


def model_code(name):
    """'Airbus A321neo' -> 'a321neo', 'Boeing 737 MAX 8' -> '737max8', 'Boeing 737-900ER' -> '737900er'."""
    s = re.sub(r"\b(airbus|boeing|embraer|bombardier|airlines?|passenger|pax)\b", "", (name or "").lower())
    return re.sub(r"[^a-z0-9]", "", s)


def match_key(name, candidates):
    """Candidate key for the same aircraft variant. One code must be a prefix of the other, so
    'A321' ~ 'A321neo' and '737' ~ '737-800' match, but 'A319' never matches 'A321'."""
    if not name or not candidates:
        return None
    code = model_code(name)
    if not code:
        return None
    best = None
    for c in candidates:
        cc = model_code(c)
        if cc == code:
            return c
        if cc and (cc.startswith(code) or code.startswith(cc)):
            # prefer the closest length (A321 -> A321neo over A321neoLR)
            if best is None or abs(len(cc) - len(code)) < abs(len(model_code(best)) - len(code)):
                best = c
    return best


def resolve_type(airline, aircraft_type):
    """(type, is_typical). Falls back to fleet.json's default type when the source gave none."""
    if aircraft_type:
        return aircraft_type, False
    default = config.fleet().get(airline or "", {}).get("default_type")
    return default, bool(default)


def make_asset_key(airline, aircraft_type):
    return f"{airline or 'UNK'}|{aircraft_type or 'Unknown'}"


def _fresh(row):
    if _partial_exterior(dict(row)):  # picked before the whole-plane rule: look again now
        return False
    age = datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])
    return age < timedelta(days=REFRESH_DAYS)


def _partial_exterior(asset):
    """A non-curated livery photo whose file name says it isn't the whole plane (commons.partial_view)."""
    return asset.get("exterior_source") != "curated" and commons.partial_view(asset.get("exterior_url"))


def _cabin_entry(airline, aircraft_type):
    """cabins.json entry for the same aircraft variant (prefix match), or None."""
    if not (airline and aircraft_type):
        return None
    cabins = config.cabins()
    same_airline = [k.split("|", 1)[1] for k in cabins if k.startswith(f"{airline}|") and not k.endswith("|*")]
    t = match_key(aircraft_type, same_airline)
    return cabins.get(f"{airline}|{t}") if t else None


def _curated(slot):
    if slot and slot.get("image_url"):
        return {"url": slot["image_url"], "link": slot.get("source_page"),
                "credit": slot.get("credit"), "source": "curated"}
    return None


# cabins.json slot -> assets column prefix.
ASSET_SLOTS = {"exterior": "exterior", "cabin": "interior", "seat": "seat", "food": "food"}


def with_curated(asset):
    """An assets row with the hand-picked photos in cabins.json laid over it (same aircraft first, then airline|*).

    fetch_asset() already prefers them, but a cached row only refreshes every REFRESH_DAYS, so without this a photo
    added or changed in cabins.json (or one the cached row picked before it existed) wouldn't show until then."""
    if not asset or not asset.get("asset_key"):
        return asset
    airline, aircraft = asset["asset_key"].split("|", 1)
    cabin = (_cabin_entry(airline, aircraft) if aircraft != "Unknown" else None) or {}
    airline_wide = config.cabins().get(f"{airline}|*") or {}
    out = dict(asset)
    if _partial_exterior(out):  # never show a belly / close-up shot; the card shows its placeholder until a re-fetch
        out.update({"exterior_url": None, "exterior_link": None, "exterior_credit": None, "exterior_source": "placeholder"})
    for slot, col in ASSET_SLOTS.items():
        img = _curated(cabin.get(slot)) or _curated(airline_wide.get(slot))
        if img:
            out.update({f"{col}_url": img["url"], f"{col}_link": img["link"], f"{col}_credit": img["credit"]})
            if col in ("exterior", "interior"):  # the only slots with a source column
                out[f"{col}_source"] = "curated"
    return out


# Commons query suffix + image kind for each interior slot.
INTERIOR_SLOTS = {"cabin": ("cabin interior", "interior"),
                  "seat": ("seats", "interior"),
                  "food": ("meal service", "interior")}


def fetch_asset(conn, airline, aircraft_type):
    name = config.airline_name(airline)
    info = config.airline(airline)
    needles = [n for n in [info.get("name"), airline] + info.get("aliases", []) if n] if info else []
    blocked = set(config.load_json("blocked_images.json") or [])
    tails = config.fleet().get(airline or "", {}).get("representative_tails", {})
    tail = tails.get(match_key(aircraft_type, tails)) if aircraft_type else None

    cabin = _cabin_entry(airline, aircraft_type) or {}
    airline_wide = config.cabins().get(f"{airline}|*") or {}

    exterior = _curated(cabin.get("exterior")) or _curated(airline_wide.get("exterior"))
    if not exterior and tail:
        exterior = planespotters.by_registration(tail, conn)
    if not exterior and airline:
        exterior = commons.search(f"{name} {aircraft_type or ''}".strip(), "exterior", conn, blocked, needles)

    slots, used = {}, set()
    for slot, (suffix, kind) in INTERIOR_SLOTS.items():
        img = _curated(cabin.get(slot)) or _curated(airline_wide.get(slot))
        if not img and airline:
            img = commons.search(f"{name} {aircraft_type or ''} {suffix}".strip(), kind, conn, blocked, needles)
            if img and img["url"] in used:  # don't show the same Commons photo in two tiles
                img = None
        if img:
            used.add(img["url"])
        slots[slot] = img or {}

    exterior = exterior or {"source": "placeholder"}
    return {
        "exterior_url": exterior.get("url"),
        "exterior_link": exterior.get("link"),
        "exterior_credit": exterior.get("credit"),
        "exterior_source": exterior["source"],
        "interior_url": slots["cabin"].get("url"),
        "interior_link": slots["cabin"].get("link"),
        "interior_credit": slots["cabin"].get("credit"),
        "interior_source": slots["cabin"].get("source", "placeholder"),
        "seat_url": slots["seat"].get("url"),
        "seat_link": slots["seat"].get("link"),
        "seat_credit": slots["seat"].get("credit"),
        "food_url": slots["food"].get("url"),
        "food_link": slots["food"].get("link"),
        "food_credit": slots["food"].get("credit"),
        "seat_layout": cabin.get("layout"),
    }


def _for_route(entry, table, airline, route):
    """Apply the airline's `routes` overrides (airline|* -> {"AMS": {...}}) when either end of the flight matches."""
    overrides = (table.get(f"{airline}|*") or {}).get("routes") or {}
    match = next((overrides[airport] for airport in route if airport in overrides), None)
    return {**entry, **match} if match else entry


def amenities_for(airline, aircraft_type, route=()):
    """(entry, is_typical). Exact airline|type (variant match) first, then airline|* ('Typical for').
    `route` is the flight's (origin, destination), for the things only one route gets."""
    table = config.amenities()
    same = [k.split("|", 1)[1] for k in table if k.startswith(f"{airline}|") and not k.endswith("|*")]
    t = match_key(aircraft_type, same) if aircraft_type else None
    if t:
        return _for_route(table[f"{airline}|{t}"], table, airline, route), False
    entry = table.get(f"{airline}|*")
    return (_for_route(entry, table, airline, route), True) if entry else ({}, False)


def get_asset(conn, airline, aircraft_type, refresh=False):
    """Cached asset row for (airline, type); fetches and upserts when missing or stale."""
    key = make_asset_key(airline, aircraft_type)
    row = conn.execute("SELECT * FROM assets WHERE asset_key=?", (key,)).fetchone()
    if row and _fresh(row) and not refresh:
        return dict(row)
    asset = {"asset_key": key, **fetch_asset(conn, airline, aircraft_type), "fetched_at": utcnow()}
    cols = list(asset)
    conn.execute(
        f"""INSERT INTO assets ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})
            ON CONFLICT(asset_key) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in cols[1:])}""",
        [asset[c] for c in cols],
    )
    conn.commit()
    return asset


def enrich_fare(conn, fare):
    """Annotate a fare dict in place (used by the live chain; no `fares` write)."""
    t, typical = resolve_type(fare.get("airline_iata"), fare.get("aircraft_type"))
    fare["aircraft_type"], fare["aircraft_is_typical"] = t, int(typical)
    fare["asset"] = get_asset(conn, fare.get("airline_iata"), t)
    fare["asset_key"] = fare["asset"]["asset_key"]
    fare["amenities"], fare["amenities_typical"] = amenities_for(fare.get("airline_iata"), t,
                                                                 (fare.get("origin"), fare.get("destination")))
    return fare


def run(conn):
    """Process every pending_enrichment fare, one lookup per distinct (airline, type)."""
    groups = conn.execute(
        """SELECT airline_iata, aircraft_type FROM fares WHERE status='pending_enrichment'
           GROUP BY airline_iata, aircraft_type"""
    ).fetchall()
    done = 0
    for g in groups:
        airline, raw_type = g["airline_iata"], g["aircraft_type"]
        t, typical = resolve_type(airline, raw_type)
        where = "status='pending_enrichment' AND airline_iata IS ? AND aircraft_type IS ?"
        try:
            asset = get_asset(conn, airline, t)
            cur = conn.execute(
                f"""UPDATE fares SET asset_key=?, aircraft_type=?, aircraft_is_typical=?, status='pending_review'
                    WHERE {where}""",
                (asset["asset_key"], t, int(typical), airline, raw_type),
            )
            done += cur.rowcount
        except Exception as e:
            log.exception("enrich %s|%s failed", airline, raw_type)
            conn.execute(f"UPDATE fares SET status='error', error=? WHERE {where}", (f"enricher: {e}", airline, raw_type))
        conn.commit()
    return done


def ensure_airline_assets(conn, codes):
    """Make sure every TPA carrier has a cached livery photo for the Airline Matrix, even with no fares yet."""
    fetched = 0
    for code in codes:
        has = conn.execute("SELECT 1 FROM assets WHERE asset_key LIKE ? AND exterior_url IS NOT NULL",
                           (f"{code}|%",)).fetchone()
        if not has:
            get_asset(conn, code, config.fleet().get(code, {}).get("default_type"))
            fetched += 1
    return fetched
