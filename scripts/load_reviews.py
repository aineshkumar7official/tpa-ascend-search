"""Load a Kaggle airline-review CSV into the `reviews` table (replaces existing rows).

    python scripts/load_reviews.py data/reviews_raw.csv [--all-airlines]

Read the dataset's license first and keep the project non-commercial.
"""
import _path  # noqa: F401

import argparse
from collections import Counter

from core.db import get_conn
from core.geo import airports
from sources.reviews import rows_from_csv

COLS = ("airline_name", "airline_iata", "route_text", "origin_iata", "dest_iata", "cabin",
        "aircraft", "rating_10", "review_date", "title", "body", "sentiment")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--all-airlines", action="store_true",
                    help="keep reviews for airlines not in airlines.json (default: drop them)")
    args = ap.parse_args()
    if not airports():
        print("warning: data/airports.csv missing - run scripts/download_reference.py first for route matching")
    conn = get_conn()
    conn.execute("DELETE FROM reviews")
    conn.execute("DELETE FROM review_summaries")
    kept, per_airline, routed = 0, Counter(), 0
    for row in rows_from_csv(args.csv):
        if not row["airline_iata"] and not args.all_airlines:
            continue
        conn.execute(f"INSERT INTO reviews ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                     [row[c] for c in COLS])
        kept += 1
        per_airline[row["airline_iata"] or row["airline_name"]] += 1
        routed += bool(row["origin_iata"] and row["dest_iata"])
    conn.commit()
    print(f"Loaded {kept} reviews ({routed} with a parsed route)")
    for code, n in per_airline.most_common():
        print(f"  {code}: {n}")
    tpa = conn.execute("SELECT COUNT(*) FROM reviews WHERE (',' || origin_iata || ',') LIKE '%,TPA,%' "
                       "OR (',' || dest_iata || ',') LIKE '%,TPA,%'").fetchone()[0]
    print(f"  touching TPA: {tpa}")
