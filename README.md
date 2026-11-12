# TPA Ascend Search

*Value the journey.* Other flights give you the prices; we show you the experience.

A Streamlit web app that watches Tampa International (TPA) for cheap **nonstop** flights and pairs each
fare with livery photos, cabin details, fees and policies, passenger reviews and fun facts. $0 to run.
Built from `tpabuildv2.md`; design follows `TPA AscendSearch Wireframes V7.2.pdf`.

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

## Deploy (free)

GitHub Actions scans twice a day and saves the database to the `data` branch; the Streamlit Cloud app reads it. No credit
card anywhere. Steps and settings: **[DEPLOY.md](DEPLOY.md)**.

## Layout

| Path | What |
|---|---|
| `app.py` | Entry point: hidden `st.navigation` + Home view (Wireframe 1) |
| `views/1_Ascend_Deals.py` | Deals: window/trip/region filters, ▼% trend, 14-day sparkline (V4 p2) |
| `views/2_Airline_Matrix.py` | Airline grid and `?airline=XX` detail (Wireframes 3–4) |
| `views/3_Ascend_Search.py` | Landing ("How do you want to fly?"), one-way results, round trip · separate legs, round trip · bundles, `?fare_id=` Cabin experience (V2 p7–10, p2) |
| `bots/` | Scouter → Enricher → Critic, and `pipeline.py` (background cycle + live chain) |
| `sources/` | fast-flights (raw payload parser), SerpApi + quota guard, Planespotters, Commons, reviews, news |
| `core/` | config/naming, db schema, dates, geo, pricing (bags/travelers), queries, theme (CSS), ui (components) |
| `data/` | Static JSON (see `TODO_VERIFY.md`), airports.csv, SQLite DB |

## Wireframes V7.2 (current design)
Changes from V7 (below still applies otherwise):
- On Home, Deals and airline-page deal cards, **Cabin experience ▾** is a button next to **Book now** (the "Baggage, food,
  entertainment" dropdown box is gone). It opens under the buttons, inside the card: **Cabin images** (The plane · Seats ·
  Food/drink, with credits), then Baggage · Food & drinks · Entertainment, then Special freebie. On Deals the price trend sits above the buttons.
- Result rows, leg rows and the full Cabin experience page use the same three cabin images (Seats falls back to the cabin photo).
- A bundle's Cabin experience shows the cabin images above Compare both flights.
- "Open full cabin experience" from an airline-page deal comes back to that airline page.

## Wireframes V7
`TPA AscendSearch Wireframes V7.pdf`. Changes from V6:
- **Fare & upgrades ▾** replaces Upgrades ▾ everywhere (Home, Deals, airline deals, one-way results, separate legs, bundles):
  Base fare · UPGRADES rows · **Your price**. Only rows with a fixed `+$X` have a checkbox; a range, "from" price or
  "Check on Google Flights" row has none, because it can't change the price.
- **Cabin experience ▾** is a second dropdown on Home and Deals cards ("Baggage, food, entertainment"), opening in the card.
  Book now sits under the dropdowns. Deals no longer uses pop-ups: the **price trend** also opens in the card.
- Result rows, leg rows and bundles show **Fare & upgrades ▾ · Cabin experience ▾ · Book now** under the row. A bundle's fare panel
  sits beside the Booking summary; its cabin panel is Compare both flights (Aircraft, Baggage, Food & drinks, Entertainment & power, Special freebie).
- Cabin experience content is **Baggage** (carry-on · checked fee) · **Food & drinks** · **Entertainment · hover a chip**, then
  **Special freebie** only when the airline has one. Legroom, the fare list and the fun fact are no longer shown there.
- **Chip pop-ups** (p20): hover or tap Wi-Fi / Seatback screen / Stream to your device / Power for details, from optional
  `amenities.json` keys `wifi_cost`, `wifi_speed`, `screen_size_in`, `entertainment_system`, `stream_app`, `stream_connect`,
  `stream_content`, `power_outlet` (missing → "Not verified yet"). A checked-bag weight can go in `checked_weight` or the policy's `first_checked.weight_limit`.
- **Airline Matrix** tiles keep one airplane photo (by request, instead of the wireframe's 2–4 photo collage).

## Wireframes 5.2
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
  The search box autocompletes: the list narrows as you type (200 ms pause, `live` text input), and only the picker reruns.
- **Round trip · separate legs (p11)**: picking an outbound opens the return list in a pop-up (`ui.return_dialog`); "Choose return →"
  and the summary's Change reopen it. The cheapest return is preselected so the summary always shows a real total.
  Summary legs show legroom · on-time % · ★ when known
  (on-time needs `delay_stats`, empty until BTS data is loaded). "Fares & prices" splits the party total per seat
  (Google prices a party as one total, so a mixed party is marked est.). "What this price buys" is a ✓ / ✕ / – list.
- **Photo credits** sit on the bottom edge of card photos (the wireframes show none, but the licenses require them).
- **Ascend Search Images**: `python scripts/import_cabin_images.py` copies the photos in `Ascend Search Images/` (resized to
  1600px JPEGs) into `static/airlines/`, records them in `data/cabins.json` and refreshes cached assets. Each flight's Cabin experience
  shows its aircraft's photo when one exists (e.g. JetBlue A220, Delta A321), else the airline's. The airline page also shows
  the Freebie photo (trading cards) and "More photos". Sources still need confirming: see `TODO_VERIFY.md`.
- **Round trip · bundles**: a table (Logo · Route · airline · Times · Total price) with Best experience / Lowest price /
  Shortest travel time chips (Experience score in the chip tooltip); Cabin experience opens Compare both flights + Booking summary.

## Wireframes V3 (card redesign)

- **Fare cards** (Home, Deals, Airline deals): price first (`$X one-way` / `round trip` / `was ~$Avg`), then route, times, airline.
  Round-trip cards show Depart / Return rows; the scan doesn't store return-leg times, so that row says "times on booking page".
- **Bags box** (V6 p15): the tag only says "Bags included", "Bags not included", "1 checked bag added" or "Bag info unavailable",
  never a separate total. Home has a **Bags included** toggle that adds 1 carry-on + 1 checked to the price; Deals and Airline cards do
  when you pick bags.
- **Upgrades ▾** (V6 p15): opens inside the bags box. Rows show only their own `+$X`, and ticking one changes the card's big price
  (`↑ +$X`). A green tick is included, a maroon tick is added. A range or "from" price can't be ticked, and a fee with no usable
  amount says "Check on Google Flights". Fees come from Google for that fare, else `airline_policies.json`.
- **Google fare options** (`sources/fare_options.py`): the price on a card is what Google Flights shows for that flight. Upgrades ▾,
  the Cabin experience panel and the airline Fees card list each fare Google offers (Basic Economy, Economy, ...) with
  `+$X` and what changes, and Google's bag fee replaces the airline-wide one. Google loads these in a browser only, so each
  lookup opens the booking page in local Chrome (2–5 s, one at a time, cached 6 hours). Cards queue a lookup in the background and
  show it on the next rerun; opening Cabin experience waits for it. Needs Chrome and `playwright`; `FARE_OPTIONS=off` in `.env` turns
  it off. Without it, or when Google lists no options, cards use the scanned price and `airline_policies.json`.
- **Price trend** (Deals, V6 p9): a "▼ X% over N days" row with a mini sparkline, comparing prices for the same departure date only
  (a route returns to "Tracking" when its window rolls to a new date). **View price trend ›** opens a pop-up: 7/14/30-day chart
  (hover/tap a day for its price and change vs. the day before), price summary, and a link to Cabin experience. Cabin experience
  on Deals cards also opens as a pop-up (V6 p8); on Home it still opens below the cards.
- **Stand-out deals** (top of Deals): fares at least 10% and $20 below the route's typical (median) price for the same
  departure date, for the selected trip type across all date windows, biggest drop first (`STANDOUT_*` in `core/queries.py`).
- **Round-trip itineraries**: each scan looks up the return flight for every airline's cheapest round trip on each
  route and date (`return_leg` on `fares`), so cards show both flights' times and Book now opens that exact pair.
- **Scanning with the lid closed**: a Mac stays awake with the lid closed only on power with an external display. Otherwise run
  `sudo scripts/keep_awake_for_scan.sh` before closing it. It turns sleep off while `bots.pipeline` runs and restores it afterward.
- **Routes from TPA**: each row is priced for the page's One-way / Round-trip toggle and opens Ascend Search under exactly its conditions:
  that airline, route, trip type and flight dates, with your saved travelers and bags. Results say they're limited to the airline, with
  **Show all airlines** to widen them. A new search from a form clears the limit.
- **Airline page** (V6 p10, p16–17): description from a template (where it's based, its alliance) unless `description` is written; Fees card
  without Change / cancel; a Cabin experience card typical for the airline; a Freebie box when one is known. Deals show Cheapest flight /
  Nonstop flight / Cheapest nonstop flight, one full-width BEST DEAL card when all three are the same flight, and a dashed placeholder for an empty slot.

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
  header, so the bar matches the wireframe and can carry the "Ascend Deals · N new" alert badge. Page files live in
  `views/`, not `pages/`: Streamlit treats a `pages/` folder as its older file-based navigation, which showed the first
  visitor after a restart a false "Page not found" pop-up. Views that switch inside a page (airline card, ← All airlines)
  use `ui.open_at_top()`, because a rerun otherwise keeps the scroll position.
- **Destinations:** `destinations.json` lists all 106 TPA nonstops from the docx (Home "To" dropdown, with seasonal / "starts …" labels); the 15 with `scan: true`
  are priced each cycle. Airlines not seen on those routes get a nonstop search on the route pass's Tuesday and Friday,
  keeping the cheaper, so every carrier has a Matrix photo and deal. (One date 14 days out could land on a holiday rush.)
- **"[N] nonstops from TPA"** = destinations in the latest scans ∪ carriers listed in `destinations.json`
  (a 15-route scan alone would undercount small carriers).
- **Bags:** 2nd checked bag reuses the 1st-bag fee (a floor), always labeled "est." with a breakdown.
- **Reviews:** Mendeley "Airline Travel Reviews Data (Skytrax)", CC BY 4.0 (`data/raw/`, gitignored).
- Policies, amenities, cabin photos and descriptions start empty on purpose: see `TODO_VERIFY.md`.
- fast-flights is pinned to 3.1.0; only `sources/flights_fast.normalize()` knows Google's payload shape.

## Tests

`pytest` — normalize fixtures, date windows, pill mapping, route parsing, review fallback, deal detection,
Tracking state, quota guard, bag totals, amenity chips, fallback labels, sort, policy freshness, news filter.
