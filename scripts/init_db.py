"""Create the SQLite schema (safe to re-run)."""
import _path  # noqa: F401

from core.config import settings
from core.db import get_conn

if __name__ == "__main__":
    get_conn().close()
    print(f"Schema ready at {settings.DB_PATH}")
