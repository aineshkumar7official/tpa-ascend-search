# Data you still need to fill (nothing here was guessed)

The app shows "Not verified yet", "Coming soon" or a gray placeholder tile until these are filled.
Restart Streamlit after editing any `data/*.json` file (loaders are cached).

## Fees & Policies entry (2026-11-07)
`TPA_Airline_Fees_and_Policies.pdf` is entered for 21 airlines: bags, seats, loyalty, food, entertainment, fun facts, policy links, HQ and alliance. It replaces the Review Draft wherever both cover a field. `checked` stays null on all of them (the card says "not yet checked") because the PDF says its figures still need confirming on each airline's site.

**Not in the PDF, still empty:** Spirit (NK), Allegiant (G4). Neither has a TPA route in `destinations.json`, so decide whether they should stay listed.

**Wireframes v6 needs data we don't have:**
- Airline page "Seat & cabin": seat width and layout. Only power outlets show today (`seat_layout` in `data/cabins.json` is empty).
- Routes table "[N] flights / week": not in any source, so that column still shows service status.
- Airline descriptions use the v6 template (where it's based, its alliance). Spirit and Allegiant have neither, so they say "coming soon". Writing a `description` replaces the template.

**v6 removed Change / cancel from the Fees card and the round-trip summary, so `change_cancel` in `airline_policies.json` isn't shown anywhere now.** The data is kept. Travelers see change and refund rules in Google's fare lists instead, where Google lists them. The PDF has no change/cancel data except Alaska's Saver vs. Main table. These have nothing: American, United, British Airways, Cayman, Edelweiss, Virgin Atlantic. All other change/cancel text comes from the Review Draft and its older sources:
- Sun Country change/cancel: 2019 schedule. The $50/$100 figures were left out.
- Alaska Saver 50% cancel credit: 2023 article.
- Breeze change/cancel: March 2024 article.
- Porter change/cancel: May 2025 guide, in CAD.
- Avianca: the draft's $210 change fee may not apply to Tampa, so it's left out.

**Kept from the Review Draft because the PDF gives no amount:**
- Breeze: carry-on $35, first bag $35–$41.
- Porter: seats from C$12.

**Flagged as third-party in the PDF, so confirm first:**
- Copa $65 Basic bag (used in bag totals).
- Delta Amsterdam Main Cabin / Comfort+ bags and seats.
- Discover $41 seat fee.
- Southwest personal item size (not entered).
- United fees and sizes (the $45 bag is used in totals when no carry-on is added).
- Virgin Light $100 bag; sources say $60–$100 (used in bag totals).
- WestJet fees and seat rules.

**Google's fare options now override these fees where it lists them** (`sources/fare_options.py`, see README). Each flight's own price, fares and bag fee come from Google; the figures below only apply when Google lists no options or the lookup hasn't run:
- Google lists one price and no options for Sun Country, Avelo, Porter, Avianca, Copa, Cayman and Discover (checked 2026-11-07), so these airlines always use the PDF's fees.
- Delta to Amsterdam: the fallback is the $45 domestic fee, but Main Basic pays $75. No Amsterdam nonstop came up on the date tested, so Google's figure for it is unconfirmed.
- Air Canada $47.25: Google showed $45 on Basic to Toronto, so the PDF's figure likely includes Canadian tax. The seat fee may be CAD.
- American: Google showed $55 on Basic and $50 on Main Cabin to Dallas, not the PDF's $45.
- United: Google showed $50, not the PDF's $45 prepaid.
- British Airways: Google showed $70 on Basic to London; the PDF has no amount.
- Copa's $65 is the Basic fare; Classic includes a bag.

**Left out of bag totals (`fee_usd` null) because the fee is a range or depends on the fare:**
- Checked bag: Frontier, Sun Country, Breeze, Avelo, Avianca, British Airways, Discover, Porter, WestJet.
- Carry-on: United, Frontier, Air Canada, Avianca, Avelo, Porter, WestJet.

**Route or aircraft may not match Tampa:**
- Air Canada: the PDF lists seatback screens and power, replacing the earlier Rouge 737 MAX 8 data ("no power"). Confirm this on the A321 and 737 MAX 8 seen at TPA.
- BA cabin data is the 787-10; Virgin is the 787-9.
- BA's policy link is the Canadian page and Edelweiss' is the Swiss page.
- Discover's fees cover U.S.–Germany generally. Cayman's table doesn't name Grand Cayman.
- Aeroméxico: the source doesn't say which fare tier the seat fee is for.
- United: fares listed only as "Boeing 737" can't show screens or streaming, because the PDF's answer depends on the variant.

**Still null in `amenities.json`:**
- Wi-Fi: Avianca, Cayman, Copa.
- Seatback screen: Avianca, and United on unlisted aircraft.
- Streaming: Delta, JetBlue, Air Canada, Aeroméxico, British Airways, Copa, Discover, Edelweiss, Virgin Atlantic, and United on unlisted aircraft. Most have seatback screens, so this may not matter.

**Policy links:**
- Virgin Atlantic: the PDF's link returned 404 on 2026-11-07, so `policy_url` is null and the card links to the homepage.
- United timed out; Avelo, Avianca, Breeze, Discover, Edelweiss and Porter refused an automated check. Open these by hand.

**Still missing everywhere:**
- Extra-legroom fees (Frontier and Porter only say a fee applies).
- Exact seat prices: most are a range, "from" or "requires fee". Delta and Southwest show no paid-seat price at all.
- Sun Country fun fact (the PDF says "Not filled in yet").
- `recently_changed` for every airline.
- Airline descriptions (section 5).

**Rendering quirk:** "What this price buys" shows a ✕ for any food text without the word "free". British Airways, Cayman, Copa and Discover get a ✕, as do Delta's flights to Amsterdam, because the PDF doesn't say their food is free, even where it probably is.

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

**Photos from `Ascend Search Images/` (2026-11-07) need the same check before the site goes public.** 81 photos for 20
airlines were imported by `scripts/import_cabin_images.py` (the file list and slot for each photo are in that script). None has
a recorded source page. Credits say the airline when the photo looks like the airline's own press or marketing image,
"SANspotter" where that watermark shows, and "source to be confirmed" otherwise. Record each source and its terms, then
fix the `credit` and `source_page` fields in `cabins.json`.

Not imported (see `SKIPPED` in the script):
- `Aeromexico/50-standard.jpg` is the same file as `Breeze Airways/images.jpeg`, a Breeze seat, so it's used for Breeze only.
- The Copa ShowPass seatback photo was also in the British Airways and Delta folders. It's used for Copa only.
- `Air Canada/Screenshot … 18.43.07.png` and `Delta Airlines/summerfb2025_west-core.jpg` show premium-cabin meals.
- Two exact duplicates (JetBlue `Snack-Service 2.jpg`, Porter `Porter_images_4 (1).jpg`).

Still no photo: American cabin, Copa food, Cayman seat, WestJet cabin (shows a Commons photo), Avelo food,
and Lufthansa (no folder).

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
