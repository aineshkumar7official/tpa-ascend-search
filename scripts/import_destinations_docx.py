"""Import TPA nonstop destinations from the Word doc into data/destinations.json.

    python scripts/import_destinations_docx.py [TPA_Nonstop_Destinations.docx]

The doc has one heading paragraph per airline ("Breeze Airways (40)") followed by a table
(Destination | Code | Status). Re-run after editing the doc. Keeps each route's existing `scan`
flag (only routes with a *current* carrier are scanned).
"""
import _path  # noqa: F401

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import docx

from core.config import DATA_DIR, ROOT

AIRLINE_CODES = {
    "Aeromexico": "AM", "Air Canada": "AC", "Alaska Airlines": "AS", "American Airlines": "AA",
    "Avelo Airlines": "XP", "Avianca": "AV", "Breeze Airways": "MX", "British Airways": "BA",
    "Cayman Airways": "KX", "Copa Airlines": "CM", "Delta Air Lines": "DL", "Discover Airlines": "4Y",
    "Edelweiss Air": "WK", "Frontier": "F9", "JetBlue": "B6", "Porter Airlines": "PD",
    "Southwest Airlines": "WN", "Sun Country Airlines": "SY", "United": "UA", "Virgin Atlantic": "VS",
    "WestJet": "WS",
}
# Doc note: "Seasonal, airline unclear" — TPA tags the airport seasonal but several airlines fly it.
SEASONAL_UNCLEAR = {"BOS", "CLE", "DTW", "GRR", "LAS", "SDF", "LGA", "PHL", "PIT", "PUJ", "SLC", "SAN", "SEA", "YYZ"}
CODE_NOTES = {"TKI": "Code unverified: one source lists McKinney as DTX.",
              "IAD": "Frontier's Washington–Dulles route is not confirmed."}
REGION_OVERRIDE = {"TKI": "Southwest"}  # OurAirports' TKI is a different (Alaska) field
STATE_REGION = {
    "Northeast": "CT ME MA NH RI VT NJ NY PA",
    "Southeast": "DE DC MD VA WV NC SC GA FL KY TN AL MS AR LA",
    "Midwest": "IL IN MI OH WI IA KS MN MO NE ND SD",
    "Southwest": "AZ NM OK TX",
    "West": "CO ID MT NV UT WY AK CA HI OR WA",
}
STATE_TO_REGION = {s: r for r, states in STATE_REGION.items() for s in states.split()}
EUROPE = {"GB", "DE", "CH", "NL", "FR", "IE", "ES", "IT"}
CARRIBEAN_LATAM = {"MX", "CO", "PA", "CR", "BS", "JM", "DO", "KY", "PR", "VI", "CU"}
STATUS_RANK = {"current": 0, "seasonal": 1, "coming_soon": 2, "suspending": 3}
DEFAULT_SCAN = {"ATL", "BOS", "BWI", "CLT", "DCA", "DEN", "DFW", "DTW", "EWR", "JFK", "LAX", "LGA", "MSP", "ORD", "PHL"}


def parse_status(text):
    """'Coming soon — Nov 20, 2026' -> ('coming_soon', 'Nov 20, 2026'); 'Current — moved…' -> ('current', 'moved…')."""
    head, _, rest = (text or "").partition("—")
    head = head.strip().lower()
    key = {"current": "current", "seasonal": "seasonal", "coming soon": "coming_soon",
           "suspending": "suspending"}.get(head, "current")
    return key, rest.strip() or None


def clean_code(raw):
    return re.sub(r"[^A-Z]", "", raw.upper())


def region_for(code, airports):
    if code in REGION_OVERRIDE:
        return REGION_OVERRIDE[code]
    row = airports.get(code)
    if not row:
        return "Other"
    country = row["iso_country"]
    if country == "US":
        return STATE_TO_REGION.get(row["iso_region"].split("-")[-1], "Other")
    if country == "CA":
        return "Canada"
    if country in EUROPE:
        return "Europe"
    if country in CARRIBEAN_LATAM:
        return "Caribbean & Latin America"
    return "Other"


def read_doc(path):
    """[(airline_code, [(city, code, status, status_note, code_note)])] in document order."""
    d = docx.Document(path)
    headings = []
    for p in d.paragraphs:
        m = re.match(r"^(.+?)\s*\((\d+)\)\s*$", p.text.strip())
        if m and m.group(1) in AIRLINE_CODES:
            headings.append((AIRLINE_CODES[m.group(1)], int(m.group(2))))
    if len(headings) != len(d.tables):
        raise SystemExit(f"{len(headings)} airline headings but {len(d.tables)} tables — doc layout changed")
    out = []
    for (code, n_expected), table in zip(headings, d.tables):
        rows = []
        for r in table.rows[1:]:
            city, raw_code, status = (c.text.strip() for c in r.cells[:3])
            key, note = parse_status(status)
            rows.append((city, clean_code(raw_code), key, note))
        if len(rows) != n_expected:
            print(f"  note: {code} heading says {n_expected} routes, table has {len(rows)}")
        out.append((code, rows))
    return out


def main(path):
    airports = {}
    with open(DATA_DIR / "airports.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["iata_code"] and (row["iata_code"] not in airports or row["scheduled_service"] == "yes"):
                airports[row["iata_code"]] = row
    old = {}
    if (DATA_DIR / "destinations.json").exists():
        old = {d["iata"]: d for d in json.loads((DATA_DIR / "destinations.json").read_text())["destinations"]}

    dests = {}
    for airline, rows in read_doc(path):
        for city, code, status, note in rows:
            d = dests.setdefault(code, {"iata": code, "city": city, "carriers": [], "carrier_status": {}})
            if len(city) > len(d["city"]):
                d["city"] = city  # prefer the more specific name ("Toronto–Pearson" over "Toronto")
            if airline not in d["carriers"]:
                d["carriers"].append(airline)
            d["carrier_status"][airline] = {"status": status, **({"note": note} if note else {})}

    out = []
    for code, d in sorted(dests.items(), key=lambda kv: kv[1]["city"]):
        statuses = [s["status"] for s in d["carrier_status"].values()]
        best = min(statuses, key=STATUS_RANK.get)
        starts = [s.get("note") for s in d["carrier_status"].values() if s["status"] == "coming_soon"]
        current = best == "current"
        entry = {
            "iata": code,
            "city": d["city"],
            "region": region_for(code, airports),
            "status": best,                       # best status across carriers
            "status_note": starts[0] if best == "coming_soon" and starts else
                           next((s.get("note") for s in d["carrier_status"].values() if s["status"] == best and s.get("note")), None),
            "seasonal": best == "seasonal" or code in SEASONAL_UNCLEAR,
            "scan": current and old.get(code, {}).get("scan", code in DEFAULT_SCAN),
            "carriers": sorted(d["carriers"]),
            "carrier_status": dict(sorted(d["carrier_status"].items())),
        }
        if code in CODE_NOTES:
            entry["code_note"] = CODE_NOTES[code]
        out.append(entry)

    doc = {"updated": date.today().isoformat(),
           "source": f"{Path(path).name} (TPA October 2026 guide + airline announcements)",
           "_note": "Generated by scripts/import_destinations_docx.py — edit the doc and re-run. "
                    "scan=true routes are priced every cycle (current routes only).",
           "destinations": out}
    (DATA_DIR / "destinations.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    by_status = {}
    for e in out:
        by_status.setdefault(e["status"], []).append(e["iata"])
    print(f"{len(out)} destinations, {sum(e['scan'] for e in out)} scanned, {len({c for e in out for c in e['carriers']})} airlines")
    for k, v in by_status.items():
        print(f"  {k}: {len(v)} {v if k != 'current' else ''}")
    gone = sorted(set(old) - set(dests))
    if gone:
        print(f"  no longer listed (removed): {gone}")
    unknown = [e["iata"] for e in out if e["region"] == "Other"]
    if unknown:
        print(f"  region unknown: {unknown}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "TPA_Nonstop_Destinations.docx")
