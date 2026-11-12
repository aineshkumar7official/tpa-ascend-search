# TPA Ascend Search — Build Guide

**TPA Ascend Search.** Tagline: *"Value the journey."* Banner line: *"Other flights give you the prices; we show you the experience."*

A web app that watches Tampa International Airport (TPA) for cheap **nonstop** flights (one-way and round-trip), pairs each fare with aircraft livery photos, cabin experience details (photos, bags, food, entertainment, legroom), airline fees and policies, passenger reviews and fun facts, and serves it all through the six-screen layout in the wireframes.

**Constraints for this build**

- $0 to run. Every data source is free with no credit card, or a local file.
- Output is the **web app only**. No Discord, Telegram, email or SMS. Alerts show inside the app.
- Python end to end.

---

## 0. Wireframe map

The wireframes define six screens. Every screen shares the same chrome: a maroon header with the "TPA Ascend Search" wordmark and "Value the journey" on the right, a nav row (Home · Ascend Deals · Airline Matrix · Ascend Search), a cream banner with the banner line, and a footer.

| Wireframe | App view | File | Notes |
|---|---|---|---|
| 1. Home | Home | `app.py` | Search form + "Cheapest nonstops out of TPA right now" (One-way / Round-trip toggle, 3 cards) + 3-column footer |
| 2. Ascend Deals | Deals | `pages/1_Ascend_Deals.py` | Filters (date window, trip type, region) + drop-% cards with 14-day trend |
| 3. Airline Matrix | Airline grid | `pages/2_Airline_Matrix.py` | 4-column grid of airline cards, "View airline" |
| 4. Airline detail | Airline detail | same file, `?airline=DL` | Fees and policies, photo library, news, reviews, 4 deal modules |
| 5. Ascend Search | Results | `pages/3_Ascend_Search.py` | Summary bar, travelers/bags, sortable result rows with expandable cabin panel |
| 6. Cabin experience | Cabin detail | same file or `?fare_id=` | Header with price + Book now, 3 cabin images, amenities, cool thing, reviews |

Naming note: the wireframes alternate between "Ascend Search" and "AscendSearch". Standardize on **TPA Ascend Search** (product) and **Ascend Search** (nav item), defined once in `core/config.py`.

---

## 1. Free stack

| Layer | Tool | Cost / limit | Key? |
|---|---|---|---|
| Fare scanning (background) | [`fast-flights`](https://pypi.org/project/fast-flights/), a reverse-engineered Google Flights client | Free, unofficial; rate-limit yourself | No |
| Booking links + live-search fallback | [SerpApi Google Flights engine](https://serpapi.com/google-flights-api) | Free plan: limited monthly searches (check your dashboard) | Yes (free signup) |
| Airport reference | [OurAirports CSV](https://davidmegginson.github.io/ourairports-data/airports.csv) | Free, public domain | No |
| Airline reference | `airlines.json` (hand-built) | Free | No |
| Exterior livery photo | [Planespotters.net photo API](https://www.planespotters.net/photo/api) (by registration) | Free; requires photographer credit + link | No |
| Photo fallback (exterior, cabin, seat, food) | [Wikimedia Commons API](https://commons.wikimedia.org/w/api.php) | Free; requires license attribution | No |
| Cabin, amenities, legroom | Local `cabins.json` + `amenities.json` (hand-curated) | Free | No |
| Fees and policies | Local `airline_policies.json`, hand-checked against each airline's site, with a `checked` date | Free | No |
| Latest news | Google News RSS search per airline via `feedparser` (headline, date, link only) **or** a hand-edited `news.json` | Free | No |
| Delay data (optional) | BTS On-Time Performance CSV (public, monthly download) loaded to SQLite | Free | No |
| Passenger reviews | Kaggle airline-review dataset (Skytrax / AirlineQuality scrape) loaded into SQLite | Free download; **check the dataset license; keep the project non-commercial** | Kaggle account |
| Review sentiment | `vaderSentiment` (local) | Free | No |
| Fun facts | Local `fun_facts.json` | Free | No |
| Database | SQLite | Free | — |
| Scheduler | APScheduler (in-process) **or** GitHub Actions cron | Free | — |
| App framework | Streamlit **≥ 1.46** (needed for `st.navigation(position="top")`; confirm your installed version supports it) | Free | — |
| Hosting (optional) | Run locally, or Streamlit Community Cloud | Free | — |

> **Optional, not $0 forever:** Ignav (flight fares + booking links) gives 1,000 free requests and then charges. Leave it out unless you want a backup source; if you add it, put it behind the same quota guard as SerpApi with a hard cap of 1,000 lifetime calls.

---

## 2. Architecture

```
                ┌──────────────────────── scheduler (every 6h) ────────────────────────┐
                │                                                                       │
[1] Scouter ──► fares (pending_enrichment) ──► [2] Enricher ──► (pending_review) ──► [3] Critic ──► (ready_to_publish)
   fast-flights                                  Planespotters                         reviews DB
   destinations.json                             Commons, cabins.json                  fun_facts.json
                                                 amenities.json                        delay_stats (optional)
                                                                                           │
                                                                                           ▼
                                  [4] Dispatcher = Ascend Search web app (reads ready_to_publish)
                                      ├─ Home            search form + cheapest nonstops
                                      ├─ Ascend Deals    drop-% cards + trend
                                      ├─ Airline Matrix  grid → airline detail
                                      └─ Ascend Search   live chain: Scouter → Enricher → Critic
                                                         + Cabin experience panel/view
```

Key ideas:

1. **Bots are plain Python functions** in `bots/`, each idempotent and driven by a `status` column. Any bot can be re-run safely.
2. **Enrichment and reviews are cached per (airline, aircraft type)**, not per fare. A Delta A321 photo is looked up once, then reused for every Delta A321 fare. This keeps you far inside every free limit.
3. **The app never calls an external API** except on Ascend Search and the optional "Get booking links" action.
4. **Presentation is separated from data.** All colors, fonts and CSS live in `core/theme.py`; all reusable page pieces live in `core/ui.py`. Pages only assemble components, which keeps the wireframe look consistent across all six views.
5. **Static content (policies, amenities, news fallback, descriptions) is data, not code**, stored in JSON files with a `checked` date shown to the user.

---

## 3. Repository layout

```
tpa-ascend-search/
├── app.py                      # Home (also defines st.navigation top nav)
├── pages/
│   ├── 1_Ascend_Deals.py
│   ├── 2_Airline_Matrix.py     # grid view + detail view (?airline=XX)
│   └── 3_Ascend_Search.py      # results + cabin experience (panel and ?fare_id=)
├── bots/
│   ├── __init__.py
│   ├── scouter.py
│   ├── enricher.py
│   ├── critic.py
│   └── pipeline.py             # run_background_cycle(), run_live_chain()
├── sources/
│   ├── flights_fast.py         # fast-flights wrapper
│   ├── flights_serpapi.py      # SerpApi wrapper + quota guard
│   ├── planespotters.py
│   ├── commons.py
│   ├── reviews.py
│   └── news.py                 # Google News RSS wrapper, cached
├── core/
│   ├── db.py                   # connection, schema init, helpers
│   ├── config.py               # settings, env vars, product name
│   ├── dates.py                # search-window generator
│   ├── geo.py                  # haversine distance
│   ├── pricing.py              # bag-fee totals, per-traveler math
│   ├── theme.py                # design tokens + CSS injection
│   └── ui.py                   # components (see §10)
├── data/
│   ├── destinations.json
│   ├── airlines.json
│   ├── airline_policies.json
│   ├── fleet.json
│   ├── cabins.json
│   ├── amenities.json
│   ├── news.json
│   ├── fun_facts.json
│   ├── airports.csv
│   └── reviews_raw.csv         # gitignored if large
├── scripts/
│   ├── init_db.py
│   ├── load_reviews.py
│   ├── load_delays.py          # optional
│   ├── download_reference.py
│   └── run_scheduler.py
├── tests/
├── .streamlit/config.toml
├── .env.example
├── requirements.txt
└── README.md
```

`requirements.txt`

```
streamlit>=1.46         # top navigation support; verify
fast-flights            # pin the exact version once it works for you
google-search-results   # SerpApi client (or just use requests)
requests
pandas
apscheduler
vaderSentiment
python-dotenv
rapidfuzz               # fuzzy route/airline matching in reviews
feedparser              # airline news RSS
```

`.env.example`

```
SERPAPI_API_KEY=
SERPAPI_MONTHLY_BUDGET=90        # set below your real free quota
HTTP_USER_AGENT=TPA-AscendSearch/0.1 (student project; contact: you@usf.edu)
DB_PATH=data/ascend.db
SCAN_INTERVAL_HOURS=6
```

---

## 4. Database schema (SQLite)

```sql
-- One row per observed fare, per scan.
CREATE TABLE IF NOT EXISTS fares (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id         TEXT NOT NULL,              -- uuid of the scan run
  scanned_at      TEXT NOT NULL,              -- ISO UTC
  origin          TEXT NOT NULL DEFAULT 'TPA',
  destination     TEXT NOT NULL,              -- IATA
  trip_type       TEXT NOT NULL CHECK (trip_type IN ('one_way','round_trip')),
  depart_date     TEXT NOT NULL,
  return_date     TEXT,                       -- NULL for one-way
  stops           INTEGER NOT NULL,           -- 0 = nonstop
  price_usd       REAL NOT NULL,              -- 1 adult, no bags
  airline_iata    TEXT,
  airline_name    TEXT,
  flight_numbers  TEXT,                       -- "DL1234" or "DL1234,DL567"
  aircraft_type   TEXT,                       -- e.g. "Airbus A321neo" (may be NULL)
  depart_time     TEXT,
  arrive_time     TEXT,
  duration_min    INTEGER,
  via_airports    TEXT,                       -- for one-stop fares, e.g. "ATL"
  search_url      TEXT,                       -- Google Flights search link (always available)
  source          TEXT NOT NULL,              -- 'fast_flights' | 'serpapi'
  asset_key       TEXT,                       -- airline_iata|aircraft_type → assets table
  review_key      TEXT,                       -- airline_iata|destination → review_summaries
  status          TEXT NOT NULL DEFAULT 'pending_enrichment'
                  CHECK (status IN ('pending_enrichment','pending_review','ready_to_publish','error')),
  error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_fares_status ON fares(status);
CREATE INDEX IF NOT EXISTS idx_fares_route  ON fares(destination, trip_type, depart_date);

-- Cheapest price per route/window per scan; drives Ascend Deals.
CREATE TABLE IF NOT EXISTS price_history (
  destination  TEXT NOT NULL,
  trip_type    TEXT NOT NULL,
  window_id    TEXT NOT NULL,                 -- e.g. 'wkend+2', 'mid+4', 'wkend+6'
  scanned_at   TEXT NOT NULL,
  min_price    REAL NOT NULL,
  nonstop_only INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (destination, trip_type, window_id, scanned_at)
);

-- Cached per airline + aircraft type. Four image slots feed the cards,
-- the airline photo library and the Cabin experience view.
CREATE TABLE IF NOT EXISTS assets (
  asset_key            TEXT PRIMARY KEY,      -- "DL|Airbus A321"
  exterior_url         TEXT,
  exterior_link        TEXT,                  -- page to link to (required by Planespotters)
  exterior_credit      TEXT,                  -- photographer / license line
  exterior_source      TEXT,                  -- 'planespotters' | 'commons' | 'placeholder'
  interior_url         TEXT,
  interior_credit      TEXT,
  interior_source      TEXT,
  seat_url             TEXT,
  seat_credit          TEXT,
  food_url             TEXT,
  food_credit          TEXT,
  seat_layout          TEXT,                  -- "3-3" from cabins.json
  fetched_at           TEXT NOT NULL
);

-- Raw reviews loaded once from the dataset.
CREATE TABLE IF NOT EXISTS reviews (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  airline_name  TEXT NOT NULL,
  airline_iata  TEXT,
  route_text    TEXT,                          -- e.g. "Tampa to New York"
  origin_iata   TEXT,
  dest_iata     TEXT,
  cabin         TEXT,
  aircraft      TEXT,
  rating_10     REAL,
  review_date   TEXT,
  title         TEXT,
  body          TEXT,
  sentiment     REAL                           -- VADER compound, -1..1
);
CREATE INDEX IF NOT EXISTS idx_reviews_airline ON reviews(airline_iata);
CREATE INDEX IF NOT EXISTS idx_reviews_route   ON reviews(airline_iata, origin_iata, dest_iata);

-- Precomputed summary the app shows.
CREATE TABLE IF NOT EXISTS review_summaries (
  review_key      TEXT PRIMARY KEY,            -- "DL|JFK" or "DL|*"
  match_level     TEXT NOT NULL,               -- 'route' | 'airline' | 'none'
  avg_rating_10   REAL,
  stars_5         REAL,
  review_count    INTEGER,
  sentiment_avg   REAL,
  highlight_pros  TEXT,                        -- short, written by code, not copied review text
  highlight_cons  TEXT,
  sample_review_ids TEXT,
  fun_fact        TEXT,
  computed_at     TEXT NOT NULL
);

-- Quota tracking for any key-limited API.
CREATE TABLE IF NOT EXISTS api_usage (
  provider  TEXT NOT NULL,
  month     TEXT NOT NULL,                     -- 'YYYY-MM'
  calls     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (provider, month)
);

-- In-app deal alerts (shown as a badge on the Ascend Deals nav item).
CREATE TABLE IF NOT EXISTS deal_alerts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT NOT NULL,
  fare_id     INTEGER NOT NULL REFERENCES fares(id),
  reason      TEXT NOT NULL,                   -- 'drop_20pct' | 'new_low' | 'under_target'
  drop_pct    REAL,
  seen        INTEGER NOT NULL DEFAULT 0
);

-- Optional watchlist (single-user app).
CREATE TABLE IF NOT EXISTS watchlist (
  destination TEXT PRIMARY KEY,
  target_usd  REAL
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
  dest           TEXT NOT NULL,                -- '*' for airline-wide at TPA
  period         TEXT NOT NULL,                -- 'YYYY-MM' or 'trailing_12m'
  ontime_pct     REAL,
  avg_delay_min  REAL,
  flights        INTEGER,
  PRIMARY KEY (airline_iata, origin, dest, period)
);

-- Live search results, so a Cabin experience view can be opened by link (?fare_id=...).
CREATE TABLE IF NOT EXISTS live_results (
  fare_id      TEXT PRIMARY KEY,               -- hash of search params + flight numbers
  payload_json TEXT NOT NULL,                  -- the normalized fare dict
  created_at   TEXT NOT NULL
);
```

**Bags and traveler count are not stored on fares.** They are applied at display time by `core/pricing.py` (see §6.1). Turn on WAL mode in `core/db.py` (`PRAGMA journal_mode=WAL;`) so the scheduler can write while the app reads.

---

## 5. Static data files

### `data/destinations.json`

The airports TPA serves **nonstop**. Curate it by hand from TPA's official route map, then let the Scouter prune anything that returns zero nonstop results for 3 scans in a row (log it, don't silently delete). The `region` field powers the Ascend Deals region filter. **The Home search "To" dropdown is populated from this file only** ("List of all nonstop destinations from TPA").

```json
{
  "updated": "2026-10-22",
  "destinations": [
    { "iata": "ATL", "city": "Atlanta",  "region": "Southeast", "seasonal": false },
    { "iata": "JFK", "city": "New York", "region": "Northeast", "seasonal": false },
    { "iata": "ORD", "city": "Chicago",  "region": "Midwest",   "seasonal": false },
    { "iata": "DEN", "city": "Denver",   "region": "West",      "seasonal": false }
  ]
}
```

Start with ~15 high-traffic routes. Expand once the pipeline is stable.

### `data/airlines.json`

```json
{
  "DL": {
    "name": "Delta Air Lines",
    "brand_color": "#003366",
    "website": "https://www.delta.com",
    "description": "2–3 sentences, in your own words, on fare style, cabin and what's included."
  }
}
```

- `description` feeds the airline detail page. Write it yourself.
- "[N] nonstops from TPA" on Airline Matrix cards is **computed** from the latest scan, not stored.
- **Logos:** the Ascend Search wireframe has a `[Logo]` tile on each result row. Use the airline logo URL that Google Flights / SerpApi already returns in results when available; otherwise render a monogram tile (IATA code in the airline's brand color). Never download or host logos copied from airline sites.

### `data/airline_policies.json`

Drives the "Fees & policies at a glance" card on the airline detail page. One entry per airline, **Economy fare**, hand-checked against the airline's own policy pages.

```json
{
  "WN": {
    "checked": "2026-11-01",
    "personal_item":   { "text": "Free · size limit", "fee_usd": 0 },
    "carry_on":        { "text": "Free / $ fee",      "fee_usd": 0 },
    "first_checked":   { "text": "$ fee · weight limit", "fee_usd": null, "each_way": true },
    "seat_selection":  { "text": "Free / from $" },
    "change_cancel":   { "text": "Free / $ fee / credit only" },
    "boarding":        { "text": "Groups / assigned seats" },
    "recently_changed": { "text": "e.g., new bag or seating policy", "date": "2026-10-15" },
    "policy_url": "https://example.com/real-policy-page"
  }
}
```

Rules:

- Fill every value with the airline's **actual** current policy; the strings above are placeholders that mirror the wireframe labels.
- `fee_usd` is a numeric estimate used only for bag-fee totals; `text` is the human-readable truth. `each_way` marks fees charged per direction.
- Always show the `checked` date and the "Full policy on [airline] website ↗" link. Fees change often; re-check at least monthly, and whenever an airline announces a change (that is what the "Recently changed" row is for).

### `data/fleet.json`

Two jobs: a fallback aircraft type when the fare source doesn't return one, and **representative tail numbers** so Planespotters can return a real livery photo (its API only accepts registration or hex code, not "airline + type").

```json
{
  "DL": {
    "default_type": "Boeing 737-900ER",
    "representative_tails": {
      "Airbus A321": "N301DN",
      "Boeing 737-900ER": "N801DZ"
    }
  }
}
```

The tails above are placeholders: look up real registrations for each (airline, type) pair on Planespotters and confirm the photo shows the current livery before you commit them. ~2 tails per airline is plenty.

### `data/cabins.json`

The Cabin experience view and the airline photo library need up to three interior images per (airline, aircraft): **cabin, seat/legroom and food/perk**.

```json
{
  "B6|Airbus A321neo": {
    "cabin": { "image_url": "https://upload.wikimedia.org/...jpg",
               "credit": "Photo: <author>, CC BY-SA 4.0, via Wikimedia Commons",
               "source_page": "https://commons.wikimedia.org/wiki/File:..." },
    "seat":  { "image_url": "...", "credit": "...", "source_page": "..." },
    "food":  { "image_url": "...", "credit": "...", "source_page": "..." },
    "layout": "Economy 3-3"
  }
}
```

Only use images whose license allows reuse with attribution (CC BY, CC BY-SA, CC0, public domain). Store the credit line verbatim from the file's metadata. The wireframes show "Photo: [photographer] / [source]" under every image group, so credits are part of the design. Any missing slot renders the gray placeholder tile from the wireframe. Spend an evening curating the ~10–15 (airline, type) pairs you see most at TPA.

### `data/amenities.json`

Feeds the "Amenities: specifics" row and the "Cool thing to check out" line. Keyed by `airline|aircraft_type`, with an `airline|*` fallback.

```json
{
  "DL|Airbus A321": {
    "carry_on": "Free",
    "food_drinks": "Free snacks and soft drinks",
    "wifi": true,
    "seatback_screen": true,
    "stream_to_device": true,
    "legroom_pitch_in": "30–31",
    "cool_thing": "One short line about a real perk or quirk, written by you"
  }
}
```

Rules:

- **Chips render only for amenities that are `true`** for that aircraft ("Shows only what this flight offers"). Never show a chip you can't back up. If a key is missing, show nothing for it (not "No").
- If no entry exists for the exact aircraft, fall back to `airline|*` and label it **"Typical for [airline]"**.
- Legroom is shown as "XX in pitch"; use the airline's published seat-pitch ranges, not guesses.
- Write `cool_thing` yourself; don't copy marketing text.

### `data/news.json`

Fallback or pinned items, used when the RSS fetch fails or you want a specific headline (e.g., a new TPA route).

```json
{ "DL": [ { "headline": "...", "url": "https://...", "source": "...", "date": "2026-10-20" } ] }
```

### `data/fun_facts.json`

Write these yourself (that's the point: it's your aviation voice). One to three per airline; the Critic rotates them.

```json
{
  "WN": ["Southwest flies an all–Boeing 737 fleet, which simplifies pilot training and maintenance."],
  "DL": ["Atlanta is Delta's largest hub."]
}
```

---

## 6. Free-tier budget and quota guard

| Source | Budget rule |
|---|---|
| fast-flights | No quota, but it's an unofficial scrape. Max **1 request every 2–4 s** with jitter, back off on errors, one scan cycle at a time. If you get blocked, slow down — don't add proxies. |
| SerpApi | Set `SERPAPI_MONTHLY_BUDGET` **below** your real plan limit. Every call goes through `quota.spend('serpapi')`, which refuses once the budget is hit. Use it only for (a) optional "Get booking links" clicks and (b) live search when fast-flights fails. |
| Planespotters | Cached per tail forever (re-check monthly). Custom `User-Agent` required; generic `python-requests` UAs may be blocked. |
| Wikimedia Commons | Cached per query. Send a descriptive `User-Agent` with contact info. |
| News RSS | One request per airline per day (about 8–12/day), cached in `airline_news`; the app never hits the feed live. |

```python
# sources/flights_serpapi.py (sketch)
def spend(conn, provider: str, budget: int) -> bool:
    month = datetime.utcnow().strftime("%Y-%m")
    row = conn.execute("SELECT calls FROM api_usage WHERE provider=? AND month=?",
                       (provider, month)).fetchone()
    used = row[0] if row else 0
    if used >= budget:
        return False
    conn.execute("""INSERT INTO api_usage(provider, month, calls) VALUES(?,?,1)
                    ON CONFLICT(provider, month) DO UPDATE SET calls = calls + 1""",
                 (provider, month))
    conn.commit()
    return True
```

Show the remaining SerpApi calls and last scan time as a small muted line in the footer (the wireframes have no sidebar).

**Scan volume math (default settings):** 15 destinations × 3 date windows × (1 one-way + 1 round-trip) = 90 fast-flights requests per cycle ≈ 4–6 minutes at 3 s spacing. Four cycles a day = 360 requests/day. Scale destinations up only after a week of clean runs. Background scans always price **1 adult, no bags** so price history stays comparable.

### 6.1 Travelers and bags (`core/pricing.py`)

The search forms have **Travelers (required)**, **Carry-on (optional)** and **Checked (optional)**, with the note "Adding bags shows the real total for your trip in the results."

- **Travelers:** pass `Passengers(adults=n)` to fast-flights in live searches (and the equivalent to SerpApi). Show the total for all travelers and, when n > 1, a small "$X per traveler" line.
- **Bags:** neither fare source reliably prices bags, so compute them: `total = fare_total + bag_fees(airline, carry_on_count, checked_count, travelers, trip_type)` using `fee_usd` from `airline_policies.json`.
  - If the fee is unknown (`null`), show the fare only, plus a note "Bag fees not included for this airline."
  - Label bag-inclusive totals **"est."** and show the breakdown on hover/expander ("Fare $X + bags ~$Y"). Bag fees vary by route, time of purchase and loyalty status; don't present them as exact.
  - For round trips, double per-bag fees where the policy has `each_way: true`.
- UI defaults: "No carry-on" and "No checked bags" on Home; "1 carry-on each" is one of the options in the Ascend Search bar.

---

## 7. Bot 1 — Scouter (`bots/scouter.py`)

**Runs:** every `SCAN_INTERVAL_HOURS` (default 6).

### 7.1 Date windows (`core/dates.py`)

Fixed, rolling windows so prices are comparable scan to scan. Each maps to a pill on the Ascend Deals page:

| window_id | Deals pill | Depart | Return (round-trip) |
|---|---|---|---|
| `wkend+2` | **Weekend** | Friday ~2 weeks out | Sunday same weekend |
| `mid+4` | **Midweek** | Tuesday ~4 weeks out | Tuesday +7 days |
| `wkend+6` | **Long weekend** | Friday ~6 weeks out | Monday +3 days |
| (live only) | **Custom** | User-picked dates | User-picked dates |

Recompute the actual dates each run from "today" in America/New_York. "Custom" is not a stored window: choosing it runs a live search and doesn't write to `price_history`.

### 7.2 Logic

```
scan_id = uuid4()
for dest in destinations:
    for window in windows:
        for trip_type in ('one_way', 'round_trip'):
            results = flights_fast.search(origin='TPA', dest=dest, window, trip_type, max_stops=0)
            if results failed:
                log + continue (do NOT fall back to SerpApi in background scans — protect the quota)
            nonstop = [r for r in results if r.stops == 0]
            insert every nonstop result into fares (status='pending_enrichment')
            insert min(price) into price_history
            sleep(random.uniform(2, 4))
detect_deals(scan_id)
```

A second scan mode runs the same loop with `max_stops=None` for the `mid+4` window only, storing results with `stops > 0`. It feeds the "Cheapest (any stops)" module on the airline detail page and keeps request volume low.

### 7.3 fast-flights wrapper (`sources/flights_fast.py`)

```python
from fast_flights import FlightQuery, Passengers, create_query, get_flights

def search(origin, dest, depart, ret=None, nonstop=True, adults=1):
    legs = [FlightQuery(date=depart, from_airport=origin, to_airport=dest,
                        max_stops=0 if nonstop else None)]
    trip = "one-way"
    if ret:
        legs.append(FlightQuery(date=ret, from_airport=dest, to_airport=origin,
                                max_stops=0 if nonstop else None))
        trip = "round-trip"
    q = create_query(flights=legs, trip=trip, seat="economy",
                     passengers=Passengers(adults=adults), currency="USD")
    result = get_flights(q)
    return normalize(result, search_url=q.url())
```

- The library's result field names change between versions. **Pin the version**, print one raw result, then write `normalize()` to map it into the `fares` columns. Keep `normalize()` the only place that knows the library's shape.
- `q.url()` gives a Google Flights link for the exact search; store it as `search_url`. That's the always-free "Book now" target.
- For round-trips, Google returns a combined price for the outbound selection; treat the listed price as the round-trip total and confirm with one manual check against the website.

### 7.4 Deal detection

After each scan, for each (destination, trip_type, window):

- `baseline` = median of `min_price` over the previous 14 days (need ≥ 6 data points, else skip). **This is the "was ~$Avg" number on Deals cards.**
- `drop_pct = (baseline - current) / baseline`.
- Insert into `deal_alerts` when `drop_pct ≥ 0.20` (`drop_20pct`), when current is the lowest ever seen (`new_low`), or when it's under a `watchlist.target_usd` (`under_target`).

---

## 8. Bot 2 — Enricher (`bots/enricher.py`)

**Runs:** right after the Scouter, then on any leftover `pending_enrichment` rows.

```
for each distinct (airline_iata, aircraft_type) among pending_enrichment fares:
    asset_key = f"{airline_iata}|{aircraft_type or fleet[airline].default_type}"
    if assets row exists and fetched_at < 30 days old: reuse
    else:
        exterior = planespotters_by_tail(fleet[airline].representative_tails[type])
                   or commons_search(f"{airline_name} {aircraft_type}", kind="exterior")
                   or placeholder
        cabin    = cabins.json[asset_key].cabin
                   or commons_search(f"{airline_name} {aircraft_type} cabin interior")
                   or placeholder
        seat     = cabins.json[asset_key].seat  or commons_search(... "seats") or placeholder
        food     = cabins.json[asset_key].food  or commons_search(... "meal service") or placeholder
        upsert assets
    UPDATE fares SET asset_key=?, status='pending_review' WHERE ...
```

Live searches also attach the matching `amenities.json` entry (or the `airline|*` fallback) so the Cabin experience panel needs no extra lookups.

### 8.1 Planespotters (`sources/planespotters.py`)

```python
URL = "https://api.planespotters.net/pub/photos/reg/{reg}"

def by_registration(reg):
    r = requests.get(URL.format(reg=reg),
                     headers={"User-Agent": settings.HTTP_USER_AGENT}, timeout=10)
    photos = r.json().get("photos", [])
    if not photos:
        return None
    p = photos[0]
    return {
        "url": p["thumbnail_large"]["src"],
        "link": p["link"],                       # must link the image to this page
        "credit": f"© {p['photographer']} / Planespotters.net",
        "source": "planespotters",
    }
```

Terms to honor in the UI: show the photographer's name next to the image, make the image link to `link`, and never put these photos behind a paywall or login.

### 8.2 Wikimedia Commons (`sources/commons.py`)

```
GET https://commons.wikimedia.org/w/api.php
  ?action=query&format=json
  &generator=search&gsrnamespace=6&gsrlimit=5
  &gsrsearch=<"JetBlue Airbus A321neo">
  &prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=800
```

- Pick the first result whose `extmetadata.LicenseShortName` is CC BY / CC BY-SA / CC0 / Public domain.
- Build the credit from `Artist` (strip HTML) + `LicenseShortName`, and link to the file description page.
- Interior results are hit-or-miss; that's why `cabins.json` comes first.

---

## 9. Bot 3 — Critic (`bots/critic.py`)

### 9.1 One-time review load (`scripts/load_reviews.py`)

1. Download an airline-review CSV from Kaggle (Skytrax / AirlineQuality-based datasets usually include airline, route text, aircraft, seat type, overall rating, review text, date). Read the dataset's license page first.
2. Map airline names → IATA with `airlines.json` + `rapidfuzz` (e.g., "Delta Air Lines" ↔ "Delta").
3. Parse `route_text` like `"Tampa to New York via Atlanta"`:
   - Split on " to " / " via ".
   - Match city names to IATA using `airports.csv` (prefer airports with scheduled service; map "New York" → {JFK, LGA, EWR} as a set).
4. Drop reviews older than ~5 years (cabins and service change).
5. Score each `body` with VADER → `sentiment`.
6. Insert into `reviews`.

### 9.2 Matching with fallback

```
for each distinct (airline_iata, destination) among pending_review fares:
    route = reviews WHERE airline_iata=? AND (
              (origin_iata='TPA' AND dest_iata=?) OR (origin_iata=? AND dest_iata='TPA'))
    if len(route) >= 3:    level='route',   pool=route
    else:
        airline = reviews WHERE airline_iata=? AND cabin LIKE 'Economy%' (last 3 years)
        if len(airline) >= 5: level='airline', pool=airline
        else:                 level='none'
    summary = {
        avg_rating_10, stars_5 = round(avg/2, 1),
        review_count, sentiment_avg,
        highlight_pros / cons = keyword tallies (see below),
        sample_review_ids = 3 most recent,
        fun_fact = rotate(fun_facts[airline_iata])
    }
    upsert review_summaries with review_key f"{airline}|{dest}" (route) or f"{airline}|*" (airline)
    UPDATE fares SET review_key=?, status='ready_to_publish'
```

**Pros/cons without copying text:** count keyword families in positive vs negative reviews (`legroom`, `crew/staff`, `on time/delay`, `wifi`, `seat`, `boarding`, `food/snacks`, `bags/fees`) and render your own phrasing, e.g. "Often praised: crew, on-time" / "Common complaints: legroom, bag fees". Show at most a short excerpt per sample review in an expander, with the source named.

The wireframe review blocks map directly to the summary fields:

- `[★ X.X / 5]` → `stars_5`
- `[N] reviews · [route-level / airline-wide]` → `review_count` + `match_level`
- `Often praised: [topics]` → `highlight_pros`
- `Common complaints: [topics]` → `highlight_cons`

**The UI label must say which level matched:** "Reviews for TPA ⇄ JFK on Delta (12)" vs "General Delta economy reviews (340)". The empty state ("No reviews yet") is acceptable; don't invent data.

### 9.3 Delay data (optional)

If `delay_stats` is loaded (`scripts/load_delays.py`, from BTS On-Time Performance files, monthly), the Critic attaches on-time % for the route or airline-wide at TPA. If you skip it, remove "Delay data" from the footer's Data sources column rather than leaving a dead label.

### 9.4 News (`sources/news.py`)

A daily scheduler job fills `airline_news` with the 3 latest headlines per airline from Google News RSS. Store headline, source, date and link only; the UI links out and never reproduces article text. Filter by airline name plus keywords to cut noise, and fall back to `news.json` if the feed fails.

---

## 10. Bot 4 — Dispatcher (the web app)

### 10.1 Design system (`core/theme.py`)

Colors below are **approximated from the wireframes**; sample them from the design files and adjust.

| Token | Approx. value | Use |
|---|---|---|
| `--maroon` | `#7F1719` | Header background, filter-panel borders, link accents, "▼ X%" badge text |
| `--cream` | `#F4E6D3` | Banner strip, "Recently changed" row, entertainment chips, drop badge background |
| `--page-bg` | `#F8F4F0` | Page background |
| `--card-bg` | `#F8F4F0` / white | Cards and panels (white for the featured/open card) |
| `--tan` | `#E2C294` | Primary buttons (Search, Book now, View airline, active pills), highlight borders on the featured card |
| `--tan-text` | near-black | Text on tan buttons |
| `--image-ph` | `#E6E9EF` | Image placeholder tiles |
| `--ink` | `#1F2328` | Body text |
| `--muted` | `#5B6470` | Secondary text |
| `--footer-bg` | `#F7F8FA` | Footer |
| `--link` | `#1A55C6` | "Book →" and footer links |
| `--gold` | tan/gold | "Value the journey" in the header |

Typography: a rounded sans for the wordmark (Nunito-style) and a clean sans for UI text (Inter-style). Load both from Google Fonts in the injected CSS, with a system-font fallback so the app still works offline.

Layout rules from the wireframes:

- Card radius ~10–12 px, 1 px light-gray border, image area on top (~45–50% of card height) then text.
- Primary action is always a tan pill/rounded-rect button; secondary actions ("Cabin experience ↓") are white with a gray border.
- Filter pills: active = tan fill, inactive = white with border.
- Three-column grid for fare/deal cards, four-column for the Airline Matrix, two-column for the airline-detail photo library.
- Every page ends with the footer and the disclaimer line.

`.streamlit/config.toml`

```toml
[theme]
base = "light"
primaryColor = "#7F1719"
backgroundColor = "#F8F4F0"
secondaryBackgroundColor = "#F7F8FA"
textColor = "#1F2328"
font = "sans serif"
```

Streamlit's defaults can't fully match the wireframes, so `theme.inject()` also writes a CSS block via `st.markdown(..., unsafe_allow_html=True)` for the header, banner, cards, pills and footer. Keep all raw HTML/CSS inside `core/theme.py` and `core/ui.py`. Hide Streamlit's default sidebar nav and use `st.navigation([...], position="top")` so the nav row sits under the maroon header with the active item underlined in tan.

### 10.2 Shared components (`core/ui.py`)

| Component | Wireframe element |
|---|---|
| `header(active)` | Maroon bar: logo + wordmark, "Value the journey", nav row |
| `banner()` | Cream strip with the banner line |
| `footer()` | 3 columns: **1. Explore** (Ascend Deals, Airline Matrix, Ascend Search), **2. About** (about the project), **3. Data sources** (fare source, delay data, photo credits); then the disclaimer: "Prices are snapshots from public fare searches and may have changed. Always confirm on the airline or booking site. Student project · USF" |
| `search_form()` | Home form: From (TPA – Tampa, fixed), To (nonstop destinations), Depart, Return, Travelers *, Carry-on, Checked, Round trip checkbox, Search |
| `search_bar_compact(params)` | Ascend Search summary: "TPA → City · dates · Round trip · Nonstop only", "Change route or dates" link, Travelers/Carry-on/Checked, **Update prices** |
| `fare_card(fare, asset)` | Home cards: livery photo, "TPA → City", price, "Airline · Nonstop", date · depart–arrive · flight time, **Book now** + **Cabin experience ↓** |
| `deal_card(fare, asset, trend)` | Deals cards: `fare_card` plus "▼ X%" badge, "was ~$Avg", 14-day sparkline |
| `airline_card(airline, n_nonstops, asset)` | Matrix tile: plane image, name, "[N] nonstops from TPA", **View airline** |
| `fees_grid(policy)` | 2×3 grid (Personal item, Carry-on bag, 1st checked bag, Seat selection, Change/cancel, Boarding) + "Recently changed" row + policy link + "Economy fare · checked [date]" |
| `photo_library(asset)` | 2×2 tiles: Exterior · livery, Cabin · economy, Seat / legroom, Food / perks, with credit line |
| `news_panel(items)` | "Latest news" list: headline · date (links out) |
| `reviews_panel(summary)` | Stars, count + match level, Often praised, Common complaints |
| `deal_modules(airline)` | Four modules: Trending, Cheapest (any stops), Cheapest nonstop, Nonstop routes list |
| `result_row(fare)` | Ascend Search row: logo tile, route · airline, depart–arrive + flight time, price, **Cabin experience ▾/▴**, **Book now** |
| `cabin_panel(fare, asset, amenities, review)` | Expanded row **and** standalone view (§10.7) |
| `credit(text, link)` | "Photo: [photographer] / [source]", always rendered next to images |

All DB reads are wrapped in `@st.cache_data(ttl=300)`. There is no sidebar: SerpApi quota and last-scan time go in a muted footer line, and unread Deal Alerts show as a badge on the "Ascend Deals" nav item.

### 10.3 Home (`app.py`) — Wireframe 1

1. **Search card** (maroon border): "Search nonstop flights from Tampa".
   - From: fixed "TPA – Tampa".
   - To: select from `destinations.json`.
   - Depart / Return date pickers; Return is disabled when "Round trip" is unchecked.
   - Travelers (required, default 1), Carry-on and Checked (optional), plus the note "* Required. Adding bags shows the real total for your trip in the results."
   - **Search** stores the inputs in `st.session_state` and navigates to Ascend Search.
2. **"Cheapest nonstops out of TPA right now"** with "Updated [time] · prices may change" and a **One-way | Round-trip** toggle (One-way default).
   - Query: cheapest fare per destination from the latest scan for the chosen trip type, top 3, one card each.
   - The first card is highlighted with the tan border (the cheapest).
   - **Book now** → `search_url`. **Cabin experience ↓** expands the cabin panel inline.
3. Footer.

### 10.4 Ascend Deals (`pages/1_Ascend_Deals.py`) — Wireframe 2

Heading "Ascend deals from TPA", subtitle "Routes whose price dropped the most compared with their recent average."

- Filter panel (maroon border): **Date window** pills (Weekend · Midweek · Long weekend · Custom), **Trip type** pills (One-way · Round-trip), **Region** select (All regions + regions from `destinations.json`).
- Query: latest scan's min price per destination vs 14-day median → `drop_pct`, sorted descending, 3-column grid of `deal_card`.
- Each card shows the ▼ X% badge, price, "was ~$Avg", a 14-day price-trend sparkline from `price_history`, dates · depart–arrive · flight time, **Book now**, **Cabin experience ▾**.
- Destinations with fewer than 6 history points show **"Tracking — trend available soon"** in place of the % badge (the wireframe carries this exact footnote).
- "Custom" opens date pickers and runs the live chain; results render as standard `result_row`s.

### 10.5 Airline Matrix (`pages/2_Airline_Matrix.py`) — Wireframes 3 and 4

**Grid view** (default): heading "Airline Matrix", subtitle "Every airline flying from TPA. Pick one to see its deals, cabin and what's included." A four-column grid of `airline_card`s (one per airline in the latest scan, with its count of distinct nonstop destinations). **View airline** sets `?airline=XX`.

**Detail view** (`?airline=XX`), two-column layout:

- Left: "← All airlines" link; airline name; "Visit [airline] website ↗"; the 2–3 sentence `description`; "**[N] nonstop routes** from TPA"; `fees_grid`; Fun fact card.
- Right: "Photo library" with the 2×2 tiles and credit line.
- Below, two panels side by side: **Latest news** (3 headlines) and **Passenger reviews**.
- "Deals on [airline] from TPA" with four modules:
  1. **Trending:** the airline's biggest ▼ % route.
  2. **Cheapest (any stops):** from the with-stops scan; shows "[1 stop via XXX]".
  3. **Cheapest nonstop** (highlighted with the tan border): "[+$X vs cheapest, saves Y min]".
  4. **Nonstop routes:** list of "[City] · from $[price]".
  Each has a **Book →** link in the link color.

If no with-stops fare exists for an airline, show "No one-stop fare found" instead of hiding the module.

### 10.6 Ascend Search (`pages/3_Ascend_Search.py`) — Wireframe 5

- Top: `search_bar_compact` with route/dates summary, **Change route or dates**, Travelers / Carry-on / Checked, and **Update prices**. Update prices re-prices the current results for new bag settings; it re-runs the search only if the traveler count changed, since that changes the fare.
- "**[N] nonstop flights found**" with **Sort: Price | Time** pills (Price default; Time = departure time).
- Results table with a header row (Logo · Route · airline · Time · Price) and one `result_row` per flight: logo tile, "TPA → [City]" with "[Airline] · Nonstop", "[Depart] – [Arrive]" with "[Flight time]", price (bag-inclusive when bags are selected, labeled est.), **Cabin experience ▾** toggle and **Book now**.
- Expanding a row shows the cabin panel inline: three images (Cabin, Seat, Perk), then Carry-on, Food & drinks, Entertainment chips, Reviews, and "Cool thing to check out".
- Empty state: "No nonstops for these dates?" with an **Include flights with stops** toggle (re-runs the search with `max_stops=None` and labels each result with its stops).
- Live chain via `pipeline.run_live_chain(params)`:

```
1. Scouter (live): fast-flights search, no DB write to fares (keeps history clean)
   └─ on failure: SerpApi search IF quota.spend('serpapi') else show "Live search unavailable — try again later"
2. Enricher: same functions, using the assets cache (usually instant)
3. Critic: same functions, using review_summaries cache, computing on the fly if missing
4. Render rows with st.status("Searching live fares…") progress steps
```

- Cache identical live searches for 15 minutes with `st.cache_data(ttl=900)`.
- Each rendered result is saved to `live_results` so its Cabin experience view is linkable.

### 10.7 Cabin experience view — Wireframe 6

Opened from "Cabin experience" (expanded inline) or as a standalone view via `?fare_id=...` (loaded from `live_results` or `fares`). Layout, top to bottom:

1. **Header card:** "TPA → [City]"; "[Airline] · Nonstop · [Aircraft type] · [Date] · [Depart – Arrive]"; price; **Book now**.
2. **Cabin experience** → **Cabin images** (3 tiles: The plane, Seats, Food/drink) + credit line.
3. **Amenities: specifics** (4 cards): Carry-on, Food & drinks, Entertainment (Wi-Fi / Seatback screen / Stream to your device chips, only those that apply, with the "Shows only what this flight offers" note), Legroom ("XX in pitch").
4. **Cool thing to check out:** the `cool_thing` line.
5. **Passenger reviews:** `[★ X.X / 5] · [N] reviews ([route / airline-wide])`, Often praised, Common complaints.
6. Footer.

Honesty rules for this screen: if the aircraft type came from `fleet.json` rather than the fare source, label it **"Typical aircraft"**; if amenities came from the `airline|*` fallback, label **"Typical for [airline]"**; if there's no review data, show "No reviews yet" rather than inventing a rating.

### 10.8 Booking links

"Book now" defaults to the free `search_url` (a Google Flights link for the exact search). An optional "Get booking links" action (a small link under Book now, not a wireframe element) spends SerpApi calls:

```
GET https://serpapi.com/search.json?engine=google_flights
    &departure_id=TPA&arrival_id=JFK&outbound_date=2026-11-13
    &type=2&stops=1&currency=USD&hl=en&api_key=...
```

- `type`: 1 = round trip, 2 = one way. `stops=1` = nonstop only.
- Results include a `booking_token`; a second request with `booking_token` returns booking options (airline and OTA links). That's 2 calls per click, so budget accordingly and cache the result on the fare row.
- If the quota is exhausted, the button falls back to `search_url`.
- Verify the current parameter names against SerpApi's docs before building.

---

## 11. Scheduling

**Option A — local (simplest):** `scripts/run_scheduler.py` uses APScheduler `BlockingScheduler` with an interval job every 6 h calling `pipeline.run_background_cycle()` (Scouter → Enricher → Critic → detect_deals), a daily job for `sources/news.py`, and (optional) a monthly job for `load_delays.py`. Run it in one terminal and `streamlit run app.py` in another. On a Mac, wrap the scheduler in a `launchd` plist so it survives restarts.

**Option B — fully hosted, still free:**
- GitHub Actions workflow on `schedule: cron: "17 */6 * * *"` runs the cycle and commits the updated `ascend.db` back to the repo (keep the DB small: prune `fares` older than 30 days, keep `price_history` forever).
- Streamlit Community Cloud serves the app from the same repo and re-reads the DB on each deploy/refresh.
- Caveat: Google may rate-limit datacenter IPs harder than your home connection. If Actions scans start failing, go back to Option A for scanning and only host the app.

Store `SERPAPI_API_KEY` in GitHub Secrets / Streamlit secrets; never commit it.

---

## 12. Attribution & compliance checklist

- [ ] Every Planespotters photo: photographer name visible next to it, and the image links to its Planespotters page.
- [ ] Every Commons image: author + license + link to the file page; credits shown under every image group ("Photo: [photographer] / [source]").
- [ ] Reviews: dataset source credited in the footer's Data sources column; only short excerpts shown; project stays non-commercial.
- [ ] Footer disclaimer on **every** page: "Prices are snapshots from public fare searches and may have changed. Always confirm on the airline or booking site."
- [ ] Fees and policies card always shows its **checked date** and a link to the airline's official policy page; bag totals are labeled **"est."**
- [ ] News: headline, source, date and link only; no article text.
- [ ] Airline logos: only URLs returned by Google Flights/SerpApi, or monogram tiles. No logos copied from airline sites.
- [ ] Delay data (if used): BTS credited in Data sources.
- [ ] Descriptive `User-Agent` with a contact email on all outbound requests.
- [ ] fast-flights is an unofficial scraper of a public site: keep scan rates low, personal/educational use.
- [ ] Footer says "Student project · USF" and has no personal or channel branding (group project).

---

## 13. Testing

| Test | How |
|---|---|
| `normalize()` for fast-flights and SerpApi | Save one raw response of each as a JSON fixture in `tests/fixtures/`; assert mapped columns. Runs offline. |
| Date windows | Freeze "today" and assert the generated dates. |
| Window mapping | Pill label → window_id; "Custom" never writes `price_history`. |
| Route-text parsing | Table of strings → expected (origin, dest) IATA. |
| Review fallback | Seed in-memory SQLite with 2 route reviews + 10 airline reviews → expect `level='airline'`. |
| Deal detection | Seed `price_history` with a flat series + one 25% drop → one `drop_20pct` alert. |
| Deals "Tracking" state | <6 history points → text shown, no % badge. |
| Quota guard | Budget=2 → third `spend()` returns False. |
| Bag-fee totals | Table of (airline, carry-ons, checked, travelers, trip type) → expected total; unknown fee returns fare only + note. |
| Amenity chips | Entry with `wifi: true, seatback_screen: false` renders only the Wi-Fi chip; a missing entry renders none. |
| Fallback labels | No exact aircraft entry → "Typical for [airline]"; fleet-default aircraft → "Typical aircraft". |
| Sort | Price and Time sorts order results correctly, ties stable. |
| Policy freshness | Warn if any `airline_policies.json` `checked` date is older than 45 days. |
| Visual check | Screenshot each of the six views at desktop width and compare against the wireframes for layout, labels and colors. |
| Smoke | `python -m bots.pipeline --dry-run --limit 2` hits real sources for 2 destinations and prints rows. |

Use `pytest`; mock all HTTP in unit tests.

---

## 14. Build plan (milestones)

### Milestone 1 — Data spine (weekend 1)
- [ ] Repo, venv, `requirements.txt` (Streamlit ≥ 1.46), `.env`
- [ ] `scripts/download_reference.py` pulls `airports.csv`
- [ ] `init_db.py` creates the schema
- [ ] `flights_fast.search()` works for TPA→ATL one-way; `normalize()` written against a saved fixture
- [ ] Scouter writes nonstop fares + `price_history` for 5 destinations

### Milestone 2 — Design system + shell (weekend 2)
- [ ] `core/theme.py` tokens and CSS; light theme in `config.toml`
- [ ] Header, banner, top nav (`st.navigation(position="top")`) and footer on all pages
- [ ] Home with search form and "Cheapest nonstops" cards using placeholder images
- [ ] Ascend Search results list (price/time sort, Book now → `search_url`)

### Milestone 3 — Enrichment + Cabin experience (week 3)
- [ ] `fleet.json` with real tails for top 5 airlines
- [ ] Planespotters + Commons sources with caching and credits
- [ ] `cabins.json` (cabin/seat/food) and `amenities.json` for the top 10 airline/aircraft pairs
- [ ] Cabin panel (inline) and standalone Cabin experience view
- [ ] Travelers + bags pricing (`core/pricing.py`) with "est." labeling

### Milestone 4 — Airline Matrix + Critic (week 4)
- [ ] Airline grid and detail page (fees grid, photo library, deal modules)
- [ ] `airline_policies.json` written and verified for every airline at TPA
- [ ] Kaggle dataset loaded, airlines + routes mapped, route → airline fallback with match-level labels
- [ ] `fun_facts.json` written (your own copy)
- [ ] News job + `airline_news`; with-stops scan for "Cheapest (any stops)"

### Milestone 5 — Deals, live search, polish (week 5)
- [ ] Scheduler running every 6 h for a full week (needed before trends mean anything)
- [ ] Ascend Deals filters, drop %, sparklines, "Tracking" state, alert badge
- [ ] Live search chain with SerpApi fallback and optional booking links
- [ ] Optional: BTS delay data

### Milestone 6 — Polish & ship
- [ ] Tests green; wireframe visual check on all six views
- [ ] README with screenshots; optional deploy (Option B)
- [ ] Record a demo of the project

---

## 15. Known risks & mitigations

| Risk | Mitigation |
|---|---|
| Google changes its Flights page and fast-flights breaks | Pin version; isolate in `normalize()`; the app keeps serving last good data with a "data is X hours old" banner; SerpApi covers live search meanwhile. |
| SerpApi free quota runs out | Hard budget guard; on-click use only; buttons degrade to `search_url`. |
| Aircraft type missing from results | `fleet.json` default type, labeled "Typical aircraft" so it's honest. |
| Sparse route reviews from TPA | Airline-level fallback is the normal case; label it clearly. |
| Commons returns the wrong plane | Prefer curated `cabins.json` and `fleet.json` tails; add a `blocked_images` list for bad hits. |
| Trends meaningless at launch | Need ~2 weeks of history; show the "Tracking" state until then. |
| Streamlit can't match the wireframes exactly | Centralize CSS in `theme.py`; accept small deviations; if the design outgrows Streamlit, the data layer is reusable behind FastAPI + a JS front end. |
| Fees/policies go stale | `checked` date on every card, a 45-day test warning, and the "Recently changed" row. |
| Bag totals are estimates | Labeled "est."; breakdown shown; unknown fees omitted with a note. |
| Amenity data wrong for a specific plane | Only show chips backed by data; "Typical for [airline]" label on fallbacks. |
| News feed noisy or irrelevant | Filter by airline name + keywords; allow `news.json` pins; fall back to the curated list. |
| Naming drift between wireframes | One source of truth: "TPA Ascend Search" in `core/config.py`. |

---

## 16. Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add SERPAPI_API_KEY
python scripts/download_reference.py
python scripts/init_db.py
python scripts/load_reviews.py data/reviews_raw.csv
python -m bots.pipeline --once  # first scan
python scripts/run_scheduler.py & # every 6h
streamlit run app.py
```
