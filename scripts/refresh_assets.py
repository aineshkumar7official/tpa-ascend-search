"""Re-fetch every cached asset (after editing fleet.json / cabins.json / blocked_images.json)."""
import _path  # noqa: F401

from bots.enricher import get_asset
from core.db import get_conn

if __name__ == "__main__":
    conn = get_conn()
    keys = [r[0] for r in conn.execute("SELECT asset_key FROM assets")]
    for key in keys:
        airline, aircraft = key.split("|", 1)
        a = get_asset(conn, airline, aircraft, refresh=True)
        print(f"{key:40} exterior={a['exterior_source']:12} cabin={a['interior_source']}")
