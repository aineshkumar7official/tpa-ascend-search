"""SQLite connection, schema and small helpers."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings

SCHEMA = """
-- One row per observed fare, per scan.
CREATE TABLE IF NOT EXISTS fares (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id         TEXT NOT NULL,
  scanned_at      TEXT NOT NULL,
  origin          TEXT NOT NULL DEFAULT 'TPA',
  destination     TEXT NOT NULL,
  trip_type       TEXT NOT NULL CHECK (trip_type IN ('one_way','round_trip')),
  window_id       TEXT,                       -- date window the fare was scanned in
  scan_mode       TEXT NOT NULL DEFAULT 'nonstop',  -- 'nonstop' | 'any' | 'airline' (Airline Matrix scans)
  depart_date     TEXT NOT NULL,
  return_date     TEXT,
  stops           INTEGER NOT NULL,
  price_usd       REAL NOT NULL,
  airline_iata    TEXT,
  airline_name    TEXT,
  flight_numbers  TEXT,
  aircraft_type   TEXT,
  aircraft_is_typical INTEGER NOT NULL DEFAULT 0,  -- 1 when type came from fleet.json
  depart_time     TEXT,
  arrive_time     TEXT,
  duration_min    INTEGER,
  via_airports    TEXT,                       -- for one-stop fares, e.g. "ATL"
  segments        TEXT,                       -- JSON [{from,to,date,flight}] -> exact-fare Book now link
  return_leg      TEXT,                       -- JSON return flight for round trips, priced the same as this fare
  search_url      TEXT,
  booking_options TEXT,                       -- cached SerpApi booking options (JSON)
  source          TEXT NOT NULL,
  asset_key       TEXT,
  review_key      TEXT,
  status          TEXT NOT NULL DEFAULT 'pending_enrichment'
                  CHECK (status IN ('pending_enrichment','pending_review','ready_to_publish','error')),
  error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_fares_status ON fares(status);
CREATE INDEX IF NOT EXISTS idx_fares_route  ON fares(destination, trip_type, depart_date);
CREATE INDEX IF NOT EXISTS idx_fares_scan   ON fares(scan_id);

CREATE TABLE IF NOT EXISTS price_history (
  destination  TEXT NOT NULL,
  trip_type    TEXT NOT NULL,
  window_id    TEXT NOT NULL,
  scanned_at   TEXT NOT NULL,
  min_price    REAL NOT NULL,
  nonstop_only INTEGER NOT NULL DEFAULT 1,
  depart_date  TEXT,                          -- windows roll forward; trends compare one departure date only
  PRIMARY KEY (destination, trip_type, window_id, scanned_at)
);

CREATE TABLE IF NOT EXISTS assets (
  asset_key            TEXT PRIMARY KEY,
  exterior_url         TEXT,
  exterior_link        TEXT,
  exterior_credit      TEXT,
  exterior_source      TEXT,
  interior_url         TEXT,
  interior_link        TEXT,
  interior_credit      TEXT,
  interior_source      TEXT,
  seat_url             TEXT,
  seat_link            TEXT,
  seat_credit          TEXT,
  food_url             TEXT,
  food_link            TEXT,
  food_credit          TEXT,
  seat_layout          TEXT,
  fetched_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  airline_name  TEXT NOT NULL,
  airline_iata  TEXT,
  route_text    TEXT,
  origin_iata   TEXT,                          -- comma list when a city maps to several airports
  dest_iata     TEXT,
  cabin         TEXT,
  aircraft      TEXT,
  rating_10     REAL,
  review_date   TEXT,
  title         TEXT,
  body          TEXT,
  sentiment     REAL
);
CREATE INDEX IF NOT EXISTS idx_reviews_airline ON reviews(airline_iata);
CREATE INDEX IF NOT EXISTS idx_reviews_route   ON reviews(airline_iata, origin_iata, dest_iata);

CREATE TABLE IF NOT EXISTS review_summaries (
  review_key      TEXT PRIMARY KEY,
  match_level     TEXT NOT NULL,
  avg_rating_10   REAL,
  stars_5         REAL,
  review_count    INTEGER,
  sentiment_avg   REAL,
  highlight_pros  TEXT,
  highlight_cons  TEXT,
  sample_review_ids TEXT,
  fun_fact        TEXT,
  computed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_usage (
  provider  TEXT NOT NULL,
  month     TEXT NOT NULL,
  calls     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (provider, month)
);

CREATE TABLE IF NOT EXISTS deal_alerts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT NOT NULL,
  fare_id     INTEGER NOT NULL REFERENCES fares(id),
  reason      TEXT NOT NULL,
  drop_pct    REAL,
  seen        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS watchlist (
  destination TEXT PRIMARY KEY,
  target_usd  REAL
);

-- One row per search the Scouter ran; used to flag routes with no nonstops.
CREATE TABLE IF NOT EXISTS scan_log (
  scan_id      TEXT NOT NULL,
  scanned_at   TEXT NOT NULL,
  destination  TEXT NOT NULL,
  window_id    TEXT NOT NULL,
  trip_type    TEXT NOT NULL,
  scan_mode    TEXT NOT NULL,
  result_count INTEGER NOT NULL,
  error        TEXT
);

-- Airline news: headline + link only, refreshed daily.
CREATE TABLE IF NOT EXISTS airline_news (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  airline_iata TEXT NOT NULL,
  headline     TEXT NOT NULL,
  url          TEXT NOT NULL,
  source       TEXT,
  published_at TEXT,
  fetched_at   TEXT NOT NULL,
  UNIQUE (airline_iata, url)
);

-- Optional on-time/delay stats from BTS data.
CREATE TABLE IF NOT EXISTS delay_stats (
  airline_iata   TEXT NOT NULL,
  origin         TEXT NOT NULL,
  dest           TEXT NOT NULL,
  period         TEXT NOT NULL,
  ontime_pct     REAL,
  avg_delay_min  REAL,
  flights        INTEGER,
  PRIMARY KEY (airline_iata, origin, dest, period)
);

-- Live search results, so a Cabin experience view can be opened by link (?fare_id=...).
CREATE TABLE IF NOT EXISTS live_results (
  fare_id      TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

-- Generic cache for outbound lookups (Planespotters per tail, Commons per query).
CREATE TABLE IF NOT EXISTS http_cache (
  cache_key   TEXT PRIMARY KEY,
  value       TEXT,
  fetched_at  TEXT NOT NULL
);
"""


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path=None):
    path = path or settings.DB_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# Columns added after a DB may already exist: (table, column, type).
MIGRATIONS = [("fares", "segments", "TEXT"), ("price_history", "depart_date", "TEXT"), ("fares", "return_leg", "TEXT")]

# Run once, in the same transaction that adds the column. Rows whose fares were already pruned stay NULL
# and so never count toward a trend.
BACKFILLS = {("price_history", "depart_date"): """
    UPDATE price_history SET depart_date=(
      SELECT f.depart_date FROM fares f
      WHERE f.destination=price_history.destination AND f.trip_type=price_history.trip_type
        AND f.window_id=price_history.window_id AND f.scanned_at=price_history.scanned_at
        AND f.scan_mode='nonstop' AND f.stops=0 LIMIT 1)"""}


def init_schema(conn):
    conn.executescript(SCHEMA)
    for table, col, typ in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            if (table, col) in BACKFILLS:
                conn.execute(BACKFILLS[table, col])
            conn.commit()
    conn.commit()


def cache_get(conn, key, max_age_days=None):
    """Return (hit, value) from http_cache. `value` is decoded JSON (may be None = cached miss)."""
    row = conn.execute("SELECT value, fetched_at FROM http_cache WHERE cache_key=?", (key,)).fetchone()
    if not row:
        return False, None
    if max_age_days is not None:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])
        if age.total_seconds() / 86400 >= max_age_days:
            return False, None
    return True, json.loads(row["value"]) if row["value"] else None


def cache_set(conn, key, value):
    conn.execute(
        """INSERT INTO http_cache(cache_key, value, fetched_at) VALUES(?,?,?)
           ON CONFLICT(cache_key) DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at""",
        (key, json.dumps(value) if value is not None else None, utcnow()),
    )
    conn.commit()


def get_conn(path=None):
    conn = connect(path)
    init_schema(conn)
    return conn
