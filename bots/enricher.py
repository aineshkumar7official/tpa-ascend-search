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
    age = datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])
    return age < timedelta(days=REFRESH_DAYS)


def _cabin_entry(airline, aircraft_type):
    """Only the same aircraft variant; a shared prefix does not prove cabin identity."""
    if not (airline and aircraft_type):
        return None
    cabins = config.cabins()
    same_airline = [k.split("|", 1)[1] for k in cabins if k.startswith(f"{airline}|") and not k.endswith("|*")]
    t = next((candidate for candidate in same_airline
              if model_code(candidate) == model_code(aircraft_type)), None)
    return cabins.get(f"{airline}|{t}") if t else None


def _curated(slot):
    if slot and slot.get("image_url"):
        return {"url": slot["image_url"], "link": slot.get("source_page"),
                "credit": slot.get("credit"), "source": "curated"}
    return None


def curated_photos(airline, aircraft_type=None):
    """Resolve each interior slot from the data file, never an unreviewed search."""
    cabin = _cabin_entry(airline, aircraft_type) or {}
    fallback = config.cabins().get(f"{airline}|*") or {}
    result = {}
    for slot, prefix in (("cabin", "interior"), ("seat", "seat"), ("food", "food")):
        photo = _curated(cabin.get(slot)) or _curated(fallback.get(slot)) or {}
        for suffix, key in (("url", "url"), ("link", "link"), ("credit", "credit")):
            result[f"{prefix}_{suffix}"] = photo.get(key)
    result["interior_source"] = "curated" if result["interior_url"] else "placeholder"
    result["seat_layout"] = cabin.get("layout") or fallback.get("layout")
    return result


def fetch_asset(conn, airline, aircraft_type):
    name = config.airline_name(airline)
    info = config.airline(airline)
    needles = [n for n in [info.get("name"), airline] + info.get("aliases", []) if n] if info else []
    blocked = set(config.load_json("blocked_images.json") or [])
    tails = config.fleet().get(airline or "", {}).get("representative_tails", {})
    tail = tails.get(match_key(aircraft_type, tails)) if aircraft_type else None

    exterior = planespotters.by_registration(tail, conn) if tail else None
    if not exterior and airline:
        exterior = commons.search(f"{name} {aircraft_type or ''}".strip(), "exterior", conn, blocked, needles)

    exterior = exterior or {"source": "placeholder"}
    return {
        "exterior_url": exterior.get("url"),
        "exterior_link": exterior.get("link"),
        "exterior_credit": exterior.get("credit"),
        "exterior_source": exterior["source"],
        **curated_photos(airline, aircraft_type),
    }


def amenities_for(airline, aircraft_type):
    """(entry, is_typical). Exact airline|type (variant match) first, then airline|* ('Typical for')."""
    table = config.amenities()
    same = [k.split("|", 1)[1] for k in table if k.startswith(f"{airline}|") and not k.endswith("|*")]
    t = match_key(aircraft_type, same) if aircraft_type else None
    if t:
        return table[f"{airline}|{t}"], False
    entry = table.get(f"{airline}|*")
    return (entry, True) if entry else ({}, False)


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
    fare["amenities"], fare["amenities_typical"] = amenities_for(fare.get("airline_iata"), t)
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
