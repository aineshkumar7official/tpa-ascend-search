"""Build data/destinations.json from data/tpa_nonstops.json (nonstops verified on Google Flights)
plus city/region from airports.csv. Hand-edit the result afterwards; `scan: true` marks the
routes the background Scouter prices every cycle (start ~15, expand once stable).

    python scripts/build_destinations.py
"""
import _path  # noqa: F401

import csv
import json
from datetime import date

from core.config import DATA_DIR

SCAN = {"ATL", "BOS", "BWI", "CLT", "DCA", "DEN", "DFW", "DTW", "EWR", "JFK", "LAX", "LGA", "MSP", "ORD", "PHL"}
STATE_REGION = {
    "Northeast": "CT ME MA NH RI VT NJ NY PA",
    "Southeast": "DE DC MD VA WV NC SC GA FL KY TN AL MS AR LA",
    "Midwest": "IL IN MI OH WI IA KS MN MO NE ND SD",
    "Southwest": "AZ NM OK TX",
    "West": "CO ID MT NV UT WY AK CA HI OR WA",
}
STATE_TO_REGION = {s: r for r, states in STATE_REGION.items() for s in states.split()}
COUNTRY_REGION = {"CA": "Canada", "GB": "Europe", "DE": "Europe", "CH": "Europe",
                  "PR": "Caribbean & Latin America"}
CITY_FIX = {"JFK": "New York", "LGA": "New York", "EWR": "Newark", "DCA": "Washington",
            "IAD": "Washington", "MSP": "Minneapolis", "DFW": "Dallas–Fort Worth", "HOU": "Houston",
            "DAL": "Dallas", "MDW": "Chicago", "ORD": "Chicago", "LHR": "London", "FRA": "Frankfurt",
            "YYZ": "Toronto", "YUL": "Montréal", "HVN": "New Haven", "ILG": "Wilmington",
            "HPN": "White Plains", "GCM": "Grand Cayman", "SJU": "San Juan", "PTY": "Panama City",
            "BOG": "Bogotá", "MEX": "Mexico City", "CUN": "Cancún", "HAV": "Havana", "CVG": "Cincinnati",
            "CAK": "Akron–Canton", "GSP": "Greenville–Spartanburg", "BDL": "Hartford", "MYR": "Myrtle Beach",
            "RDU": "Raleigh–Durham", "SDF": "Louisville", "PVD": "Providence", "PWM": "Portland, ME",
            "BWI": "Baltimore", "BTV": "Burlington", "BGR": "Bangor", "MHT": "Manchester", "SLC": "Salt Lake City"}

if __name__ == "__main__":
    nonstops = json.loads((DATA_DIR / "tpa_nonstops.json").read_text())["destinations"]
    ap = {}
    with open(DATA_DIR / "airports.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["iata_code"] in nonstops and row.get("scheduled_service") == "yes":
                ap[row["iata_code"]] = row
    out = []
    for iata, carriers in sorted(nonstops.items()):
        row = ap.get(iata, {})
        country, region_code = row.get("iso_country", ""), row.get("iso_region", "")
        if country == "US":
            region = STATE_TO_REGION.get(region_code.split("-")[-1], "Other")
        else:
            region = COUNTRY_REGION.get(country, "Caribbean & Latin America")
        out.append({"iata": iata, "city": CITY_FIX.get(iata, row.get("municipality") or iata),
                    "region": region, "seasonal": False, "scan": iata in SCAN, "carriers": carriers})
    doc = {"updated": date.today().isoformat(),
           "_note": "TPA nonstops from tpa_nonstops.json; verify against TPA's route map. scan=true routes are priced every cycle.",
           "destinations": out}
    (DATA_DIR / "destinations.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(out)} destinations, {sum(d['scan'] for d in out)} scanned")
    for r in sorted({d['region'] for d in out}):
        print(" ", r, [d["iata"] for d in out if d["region"] == r])
