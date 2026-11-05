# TPA Ascend Search — by AK Aviation

*Value the journey.* Other flights give you the prices; we show you the experience.

A Streamlit web app that watches Tampa International (TPA) for cheap **nonstop** flights and pairs each
fare with livery photos, cabin details, fees and policies, passenger reviews and fun facts. $0 to run.
Built from `tpabuildv2.md`; design follows `TPA AscendSearch Wireframes 5.2.pdf`.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # optional: add SERPAPI_API_KEY
python scripts/init_db.py
python scripts/import_destinations_docx.py   # TPA_Nonstop_Destinations.docx -> data/destinations.json
python scripts/load_reviews.py data/raw/skytrax_reviews.xlsx
python -m bots.pipeline --once             # first scan (~8 min, rate-limited)
python -m bots.pipeline --news             # first news pull
python scripts/run_scheduler.py &          # scans every 6 h, news daily
streamlit run app.py
```

`python -m bots.pipeline --dry-run --limit 2` hits real sources for 2 destinations and prints rows.

## Layout

| Path | What |
|---|---|
| `app.py` | Entry point: hidden `st.navigation` + Home view (Wireframe 1) |
| `pages/1_Ascend_Deals.py` | Deals: window/trip/region filters, ▼% trend, 14-day sparkline (V4 p2) |
| `pages/2_Airline_Matrix.py` | Airline grid and `?airline=XX` detail (Wireframes 3–4) |
| `pages/3_Ascend_Search.py` | Landing ("How do you want to fly?"), one-way results, round trip · separate legs, round trip · bundles, `?fare_id=` Cabin experience (V2 p7–10, p2) |
| `bots/` | Scouter → Enricher → Critic, and `pipeline.py` (background cycle + live chain) |
| `sources/` | fast-flights (raw payload parser), SerpApi + quota guard, Planespotters, Commons, reviews, news |
| `core/` | config/naming, db schema, dates, geo, pricing (bags/travelers), queries, theme (CSS), ui (components) |
| `data/` | Static JSON (see `TODO_VERIFY.md`), airports.csv, SQLite DB |

## Wireframes 5.2 (current design)
Changes from V5.1 (pages 6, 7, 9, 11, 13); everything else below still applies:
- Passenger reviews are no longer shown on the cabin experience page and panel, airline page, round-trip leg cards or Compare both flights. Reviews are still collected and still count toward the Experience score.
- "Cool thing to check out" is now **Special freebies** (data key is still `cool_thing`).
- Latest news is full width on the airline page.
- Kept on purpose: compact box sizes (not the wireframes' roomier spacing), and the Change / cancel fee table.

## Wireframes V5.1 (airline page)

V5.1 changes only the airline page (p7–8); every other page follows V4 below. The whole app also runs narrower and tighter
than the wireframes (content max 1080px), by request.

- **Routes from TPA**: every row searches that route in Ascend Search, using the saved dates, travelers and bags and the
  page's One-way / Round-trip toggle.
- **Deals**: One-way / Round-trip toggle plus Cheapest flight (any stops), Nonstop flight (fastest) and Cheapest nonstop flight
  (`queries.airline_deals`). An empty slot keeps a dashed placeholder. Scans only collect fares with stops for one-way trips, so
  a round-trip "Cheapest flight" is drawn from nonstops.

## Wireframes V4 (13 pages)

- **Look**: Inter (set in `.streamlit/config.toml`), Nunito for the wordmark, ink prices, white form fields. Content fills the
  page with the header, banner and footer on the same left edge. The three-column footer is on Home only.
- **To picker (p5)**: search box, A–Z list, Clear / Done · N airports. New York (JFK/LGA/EWR), Chicago (ORD/MDW), Washington
  (DCA/IAD/BWI), Houston (IAH/HOU) and Dallas (DFW/DAL) have checkboxes (`config.METROS`); every other city is a single tap.
  Codes: all ticked `ALL_NYC`, some ticked `ALL_NYC:JFK,EWR`, one ticked `JFK` (`config.selection_code`). Ticks stay within one
  city. A search runs once per airport and merges; headers say "(All airports · …)" or "(JFK, EWR)". Coming-soon airports aren't searched.
  The search box filters on Enter (Streamlit text inputs don't report keystrokes).
- **Round trip · separate legs (p11)**: picking an outbound opens the return list in a pop-up (`ui.return_dialog`); "Choose return →"
  and the summary's Change reopen it. The cheapest return is preselected so the summary always shows a real total.
  Summary legs show legroom · on-time % · ★ when known
  (on-time needs `delay_stats`, empty until BTS data is loaded). "Fares & prices" splits the party total per seat
  (Google prices a party as one total, so a mixed party is marked est.). "What this price buys" is a ✓ / ✕ / – list.
- **Photo credits** sit on the bottom edge of card photos (the wireframes show none, but the licenses require them).
- **Round trip · bundles**: a table (Logo · Route · airline · Times · Total price) with Best experience / Lowest price /
  Shortest travel time chips (Experience score in the chip tooltip); Cabin experience opens Compare both flights + Booking summary.

## Wireframes V3 (card redesign)

- **Fare cards** (Home, Deals, Airline deals): price first (`$X one-way` / `round trip` / `was ~$Avg`), then route, times, airline.
  Round-trip cards show Depart / Return rows; the scan doesn't store return-leg times, so that row says "times on booking page".
- **Bags box**: "Bags included · …" or "Bags not included · $Total with bags" (your bags, or 1 carry-on + 1 checked when none are picked).
  Home has a **Bags included** toggle that puts that total in the headline; Deals and Airline cards include bags when you pick some.
- **Upgrades ▾**: add checked bag / choose seat / extra legroom as `+$X → $New total`, from `airline_policies.json`
  (`first_checked.fee_usd`, `seat_selection.fee_usd`, `extra_legroom.fee_usd`); unknown fees show "Not verified yet".
- **Price trend** (Deals, Airline Trending): "▼ X% over 14 days" row with a mini sparkline that opens a daily-price chart
  (hover/tap a day for its price and change vs. the day before; low/high; Airline Trending adds 7/14/30-day tabs). Pure HTML/CSS.
- **Airline page deals**: full cards with TRENDING / CHEAPEST (ANY STOPS) / CHEAPEST NONSTOP tags; empty slots keep a dashed placeholder.

## Wireframes V2

- **Travelers** = Adults (12+) / Children (2–11) / Infants (under 2, on a lap) in a popover; infants ≤ adults, 9 max.
  Live searches price the whole party; Book now links carry the same passengers.
- **Bags are totals for the trip** (not per traveler), shown in cream boxes; cards say "Price includes …" or "Bags not included".
- **Round trip · separate legs**: outbound list (prices = cheapest round-trip total), then Google's return list for the chosen
  outbound (1 live request); summary card with what the price buys, fare/bag breakdown and Book now for that exact pair.
- **Round trip · bundles**: returns are priced for the 4 best outbounds (cheapest per airline first; 4 requests) and ranked by
  `core/experience.py` — Experience score = verified comfort (≤4) + reviews (≤3) + flight time (≤3), unknowns at half credit.
- Taxes are included in Google's fare, so the breakdown shows "Taxes & fees: Included in fare".
- **Airline page · Routes from TPA** (p6): no source gives weekly frequency, so the "[N] flights / week" column shows the
  carrier's service status from the docx (Year-round / Seasonal / Starting soon / Ending soon) instead.

## Notes and deviations from the build guide

- **Navigation:** `st.navigation(position="hidden")` plus a custom nav row of `st.page_link`s inside the maroon
  header, so the bar matches the wireframe and can carry the "Ascend Deals · N new" alert badge.
- **Destinations:** `destinations.json` lists all 106 TPA nonstops from the docx (Home "To" dropdown, with seasonal / "starts …" labels); the 15 with `scan: true`
  are priced each cycle. Airlines not seen on those routes get one nonstop search 14 days out so every
  carrier has a Matrix photo.
- **"[N] nonstops from TPA"** = destinations in the latest scans ∪ carriers listed in `destinations.json`
  (a 15-route scan alone would undercount small carriers).
- **Bags:** 2nd checked bag reuses the 1st-bag fee (a floor), always labeled "est." with a breakdown.
- **Reviews:** Mendeley "Airline Travel Reviews Data (Skytrax)", CC BY 4.0 (`data/raw/`, gitignored).
- Policies, amenities, cabin photos and descriptions start empty on purpose: see `TODO_VERIFY.md`.
- fast-flights is pinned to 3.1.0; only `sources/flights_fast.normalize()` knows Google's payload shape.

## Tests

`pytest` — normalize fixtures, date windows, pill mapping, route parsing, review fallback, deal detection,
Tracking state, quota guard, bag totals, amenity chips, fallback labels, sort, policy freshness, news filter.
