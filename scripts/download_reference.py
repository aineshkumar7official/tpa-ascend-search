"""Download reference data: OurAirports airports.csv (public domain)."""
import _path  # noqa: F401

import requests

from core.config import DATA_DIR, settings

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

if __name__ == "__main__":
    dest = DATA_DIR / "airports.csv"
    r = requests.get(AIRPORTS_URL, headers={"User-Agent": settings.HTTP_USER_AGENT}, timeout=60)
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"Saved {len(r.content) / 1e6:.1f} MB to {dest}")
