# Data you still need to fill (nothing here was guessed)

The app shows "Not verified yet", "Coming soon" or a gray placeholder tile until these are filled.
Restart Streamlit after editing any `data/*.json` file (loaders are cached).

## Review draft entry (2026-11-05)
`TPA Airline Profiles – Review Draft.pdf` is entered for 20 airlines plus the earlier Frontier preview. `checked` stays null on all of them (the card says "not yet checked") until each is confirmed on the airline's own site.

**Not in the draft, still empty:** Spirit (NK), Allegiant (G4).

**Unconfirmed in the draft, so left out of bag totals (`fee_usd` null):**
- JetBlue Main Base carry-on: only a news report says it's included.
- Avianca Basic carry-on: Avianca's page and a 2024 guide conflict.
- United Basic carry-on, seat, change and cancel rules: check on united.com.

**Older or indirect sources:**
- Sun Country change/cancel: 2019 schedule. The $50/$100 figures were left out.
- Alaska Saver rules: 2023 article.
- Breeze change/cancel: March 2024 article.
- Porter change/cancel: May 2025 guide, in CAD.
- Air Canada seat fee: may be CAD.
- Avianca: the draft's $210 change fee may not apply to Tampa, so it's left out.

**Route or aircraft may not match Tampa:**
- Air Canada cabin data is the Rouge 737 MAX 8 only. It's stored airline-wide, including "no power", and it would be wrong if mainline aircraft start flying TPA.
- BA cabin data is the 787-10; Virgin is the 787-9.
- BA fees come from its long-haul page. Discover's cover U.S.–Germany generally. Cayman's table doesn't name Grand Cayman.
- Aeroméxico: the source doesn't say which fare tier the seat fee is for.
- Delta airport first-bag fee: sources say $45 or $50.

**Left null because the draft says it varies by layout** (needs per-aircraft `XX|type` entries):
- Copa: Wi-Fi, screens, streaming, power
- United: screens, streaming, power
- Southwest: power
- Edelweiss: Wi-Fi, power
- Avianca: Wi-Fi (rollout in progress)
- Cayman: Wi-Fi (TBC)

**Still missing:** extra-legroom fees for every airline, exact seat prices, `policy_url`, food for 11 airlines, and fare-specific rules for the "Not verified yet" cells.

## 1. `data/airline_policies.json` (Fees & policies card + bag totals)
For each airline, Economy fare, from the airline's own policy page:
- `text` for personal item, carry-on, 1st checked bag, seat selection, change/cancel, `loyalty_program` (V2 shows it instead of boarding)
- `fee_usd` for carry-on and 1st checked bag (numbers, used only for "est." bag totals; leave null if unsure)
- `each_way: true` when the fee is charged per direction
- `seat_selection.fee_usd` (cheapest standard seat) and `extra_legroom.fee_usd` (cheapest extra-legroom seat), per traveler per flight — used by the card **Upgrades** menu
- `policy_url` (the real policy page), `checked` (today's date), `recently_changed` when an airline announces a change
- A test-style warning shows in the card when `checked` is over 45 days old.

## 2. `data/amenities.json` (Cabin experience panel)
Start with `XX|*` for each airline, then add exact `XX|Aircraft type` entries for common TPA aircraft.
- `wifi`, `seatback_screen`, `stream_to_device`, `power`: `true` only when you can back it up (chips only render for `true`)
- These also drive the round-trip **Experience score** — unverified items count half, so filling them in sharpens the ranking
- `legroom_pitch_in` from the airline's published seat pitch (e.g. "30–31")
- `carry_on`, `food_drinks`: short text; `cool_thing`: one free perk, shown as **Special freebies**

## 3. `data/cabins.json` (cabin / seat / food photos)
`image_url`, `credit` (verbatim from the file page) and `source_page` for CC BY / CC BY-SA / CC0 / public-domain Commons files.
Empty slots fall back to an automatic Commons search, then to the gray placeholder.
Then run `python scripts/refresh_assets.py` to re-fetch cached assets.

**Frontier (`F9|*`) images need rights confirmed before the site goes public.** They came from the `Frontier Airlines` folder and don't meet the license rule above yet:
- `static/airlines/F9/cabin.jpg`: from Frontier's newsroom media library (news.flyfrontier.com); usage terms not confirmed.
- `static/airlines/F9/seat.jpg`: from the same media library; usage terms not confirmed.
- `static/airlines/F9/food.jpg`: downloaded from Frontier's website; Frontier's own artwork.

## 4. `data/fleet.json` representative tails
Tails for DL, WN, B6, AA, NK are unverified starting points copied from AeroPulse; UA, F9, AS, SY, MX, G4, AC have none.
Confirm each on planespotters.net shows the current livery.

## 5. Your own words
- `data/airlines.json` → `description` (2–3 sentences per airline)
- `data/fun_facts.json` → starter facts are placeholders; rewrite in your aviation voice, add more airlines
- Footer "About" column → add the AK Aviation channel links in `core/ui.py` `footer()`

## 6. `data/destinations.json`
Generated from `TPA_Nonstop_Destinations.docx` by `python scripts/import_destinations_docx.py` (106 airports, 21 airlines).
Edit the doc and re-run rather than editing the JSON. Open items from the doc:
- **McKinney (TKI)** — code unverified (one source says DTX); OurAirports' TKI is a different airport, so its region is hard-set.
- **Frontier Washington–Dulles (IAD)** — not confirmed.
- Seasonal tags come from an older copy of TPA's page.
Flip `scan: true` on more current routes once a week of scans runs clean.
