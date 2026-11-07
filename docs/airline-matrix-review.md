# Airline Matrix review — 2026-11-06

This is an incomplete verification pass. Do not treat every airline as verified or merge as a completed Matrix.

## Sources and policy scope

Each confirmed policy field in `data/airline_policies.json` records its official `source_url` and `checked` date. Other existing values remain draft data. The UI labels these separately. Descriptions also record their official source. The airline-wide `checked` dates remain unset because whole profiles have not been verified.

Official pages were checked one airline at a time. Initial coverage:

| Airline | Confirmed scope | Still needs checking |
| --- | --- | --- |
| Delta | Bags, Main Basic assignment, change/cancel qualifications | Loyalty, specific aircraft amenities, freebies, routes |
| Southwest | Basic seat assignment and upgrade required for changes | Bag fee source conflicts, cancellation details, cabin amenities |
| JetBlue | All-fare carry-on, seat assignment, Base change/cancel | Date-specific checked bag pricing, amenities |
| American | Personal item, carry-on, eligible-route Basic first checked bag | Change/cancel, seating exceptions, amenities |
| United | Basic seat assignment, bag calculator, domestic Basic carry-on restriction | Route/traveler exceptions, ticket flexibility, aircraft amenities |
| Spirit | Official operations wind-down notice | Keep historic fares from being presented as current elsewhere |
| Frontier | Current change/cancel schedule, carry-on charged or bundled | Personal-item and checked-weight details, amenities/freebies |
| Alaska | Saver cabin bags, seats, cancellation and same-day qualifications | Current checked bag pricing, amenities |
| Sun Country | Personal item, paid bags/seats, streaming entertainment | Current fee amounts, ticket flexibility |
| Breeze | Current bundles including Nice carry-on, No Flex restrictions | Exact cancellation-credit schedule, variable bag prices |
| Allegiant | Personal item, paid bags and route/timing variability | Seat and flexibility rules, current TPA relevance |
| Air Canada | Basic cabin bag restrictions and variable checked allowance | TPA fare conditions, aircraft-specific cabin (draft is Rouge-only) |
| Aeroméxico | Fare-dependent cabin baggage | TPA-specific fare rules, checked bags and seating |
| Avianca | Lowest international Americas fare carry-on | Current fare name on TPA routes, seats, checked bags, changes |
| Avelo | Current Standard penalty range and one-use AveloFlex | Bags, seats, amenities |
| British Airways | Basic seat allocation/payment | Bags, ticket flexibility, TPA aircraft |
| Cayman | TPA first checked bag and international cabin baggage | Seats and flexibility |
| Copa | Basic carry-on, paid checked bags, paid seat choice | Route calculator, changes/refunds, TPA aircraft |
| Discover | Economy carry-on and Light checked-bag exclusion, long-haul meals | New fare families, seat/flexibility details |
| Edelweiss | Long-haul baggage, seat fees, Saver change/cancel | Personal-item details, aircraft amenities |
| Porter | Basic bags, seats, change/refund limitations, refreshments | Assigned seat details and exact fees, aircraft amenities |
| Virgin Atlantic | Cabin and checked allowance by economy fare | Seats, ticket flexibility, aircraft amenities |
| WestJet | UltraBasic cabin-bag exceptions | Seats, checked bags, ticket flexibility, aircraft amenities |

## Images

Cabin/seat/perk slots now resolve exclusively from `data/cabins.json`. They no longer use broad Commons searches, which cannot reliably distinguish economy seating or a matching perk. The Matrix detail reads curated images even when the local SQLite database has no asset row. Exterior API records for four airlines are included in `data/exteriors.json` so a fresh checkout can display them without running a flight scan.

The repository contains only three populated curated photo slots, all for Frontier. The profiles PDF contains text but no image assets or image hyperlinks. The separate cabin/seat/perk source data file still needs to be identified by the user. Existing local livery JPG files have no attribution manifest and have not been silently substituted for API results.

Planespotters registration responses for Delta N801DZ, Southwest N8301J, JetBlue N2002J and American N901NN returned airline/type-specific photo-page URLs matching their assigned airline and aircraft. The other 17 attempted registration endpoints returned HTTP 403; this is recorded as a retrieval limitation, not proof that a registration belongs to an airline. Do not add those unconfirmed registrations to fleet data.

Run `.venv/bin/python scripts/audit_matrix.py --online` to produce `data/matrix_audit.json`. The audit uses the same asset selector as the Matrix page, GETs remote images and decodes image bytes. Exit 1 is expected while any slot is absent/broken. A decoded image still requires visual identity review. Frontier's three local curated images were visually inspected: cabin rows, Frontier-branded seats, and Frontier-branded snack packs. Source licensing notes in TODO_VERIFY.md still apply.

## Remaining completion gates

- Identify the user's cabin/seat/perk source file and populate all matching image entries.
- Obtain the remaining API exterior records and inspect each livery.
- Finish all unverified policy, amenity, route-count and fun-fact fields against official sources.
- Resolve layout/type-specific amenities without asserting them across an entire airline.
- Visually inspect the full grid and every detail library in the browser.
- Rerun the image audit with no missing/broken slots, and record visual identity review separately.

## Validation

89 tests passed. Streamlit AppTest rendered the grid and Delta, Frontier and Spirit details without exceptions. The online image audit found 5 decodable exteriors and 3 decodable curated images in the local database; the other slots remain missing. No flight scan, scheduler, filtering or booking popup changes were included.
