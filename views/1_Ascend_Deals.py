"""Ascend Deals — Wireframes V4 p2. Stand-out price drops first, then the fares for the chosen filters."""
from datetime import date, timedelta

import streamlit as st

from bots.scouter import MIN_POINTS
from core import config, pricing, queries, ui

ui.chrome(config.NAV_DEALS)
queries.mark_alerts_seen(ui.conn())
ui.heading("Ascend deals from TPA", "Routes whose price dropped the most compared with their recent average. "
           "Open a card's dropdowns for fare &amp; upgrades, cabin experience and price trend.")

s = ui.search_state()
with st.container(key="panel_filters"):
    c1, c2, c3 = st.columns([2.6, 1.5, 1.4], gap="medium")
    window_label = c1.pills("Date window", list(queries.WINDOW_PILLS), default="Weekend", key="deal_window") or "Weekend"
    trip_label = c2.pills("Trip type", list(queries.TRIP_PILLS), default="One-way", key="deal_trip") or "One-way"
    with c3:
        party = ui.travelers_control("deal", s["party"])
    b1, b2, b3 = st.columns([2.05, 2.05, 1.4], gap="medium", vertical_alignment="bottom")
    with b1:
        st.markdown('<div class="stp-label">Bags <span class="muted">(optional)</span></div>', unsafe_allow_html=True)
        carry = ui.bag_control("deal", "carry_on", s["carry_on"], party)
    with b2:
        checked = ui.bag_control("deal", "checked", s["checked"], party)
    region = b3.selectbox("Region", ["All regions"] + config.regions(), key="deal_region")
    custom = None
    if window_label == "Custom":
        d1, d2, d3, d4 = st.columns([1, 1, 1.4, 1], vertical_alignment="bottom")
        dep = d1.date_input("Depart", date.today() + timedelta(days=21), min_value=date.today(), format="MM/DD/YYYY")
        ret = d2.date_input("Return", dep + timedelta(days=3), min_value=dep, format="MM/DD/YYYY",
                            disabled=trip_label == "One-way")
        dests = [d["iata"] for d in config.destinations()
                 if (region == "All regions" or d.get("region") == region) and d.get("status") != "coming_soon"]
        dest = d3.selectbox("To", dests, format_func=ui.dest_label)
        if d4.button("Search live", type="primary", width="stretch"):
            custom = {"destination": dest, "depart_date": dep.isoformat(),
                      "return_date": ret.isoformat() if trip_label == "Round-trip" else None,
                      "party": party.as_dict(), "nonstop": True}

trip_type = queries.TRIP_PILLS[trip_label]
st.write("")

if window_label == "Custom":
    # Custom is live-only: runs the live chain and never writes price_history.
    if custom:
        st.session_state["deal_custom"] = custom
    params = st.session_state.get("deal_custom")
    if not params:
        st.markdown('<div class="muted">Pick dates and a destination, then <b>Search live</b>.</div>',
                    unsafe_allow_html=True)
    else:
        from bots import pipeline

        with st.status("Searching live fares…", expanded=False) as status:
            res = pipeline.run_live_chain(params, ui.conn(), progress=lambda msg: status.update(label=msg))
            status.update(label=f"{len(res['fares'])} nonstop flights found", state="complete")
        if res["error"]:
            st.warning(res["error"])
        quotes = [(f, pricing.quote(f, carry, checked, party)) for f in res["fares"]]
        shown = sorted(((f, qt) for f, qt in quotes if qt.bags_total is not None), key=lambda x: x[1].total)
        with st.container(key="restable_deals"):
            for f, qt in shown:
                ui.result_row(f, qt, scope="dealres")
        ui.hidden_note(len(quotes) - len(shown))
else:
    window_id = queries.window_for_pill(window_label)
    region_arg = None if region == "All regions" else region
    items = ui.q("deals", window_id, trip_type, region_arg, carry, checked, party)
    standouts = ui.q("standout_deals", trip_type, region_arg, carry, checked, party)

    def render(d):
        ui.deal_card(d, ui.card_price(d["fare"], party, carry, checked, bool(carry or checked)), "deals")

    ui.heading(f"Stand-out deals · {trip_label}", f"At least {queries.STANDOUT_MIN_DROP:.0%} and "
               f"&#36;{queries.STANDOUT_MIN_SAVINGS_USD} below the route's typical price for the same departure date. "
               "Includes all date windows.", level=2)
    if standouts:
        ui.card_grid(standouts, render)
    else:
        st.markdown(f'<div class="muted">No {trip_label.lower()} stand-out deals right now: no route has dropped enough yet.</div>',
                    unsafe_allow_html=True)
    st.write("")
    ui.heading(f"{window_label} fares · {trip_label}", level=2)
    if not items and ui.q("deals", window_id, trip_type, region_arg):
        st.info("No deals with these bags: bag fees aren't verified for the airlines in this window.")
    elif not items:
        st.info("No fares for this window yet. Deals appear after the background scans run.")
    else:
        featured = {d["fare"]["fare_id"] for d in standouts}  # already shown above, so don't show them twice
        rest = [d for d in items if d["fare"]["fare_id"] not in featured]
        if rest:
            ui.card_grid(rest, render)
        else:
            st.markdown('<div class="muted">All of these are in Stand-out deals above.</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="credit" style="margin-top:1rem">Routes with fewer than {MIN_POINTS} price checks show '
                '“Tracking — trend available soon” instead of a % drop. Trends only compare prices for the same '
                'departure date, so a route goes back to Tracking when its date moves forward.</div>', unsafe_allow_html=True)

ui.footer()
