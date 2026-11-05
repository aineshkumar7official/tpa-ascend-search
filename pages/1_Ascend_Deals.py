"""Ascend Deals — Wireframes V4 p2. Routes whose price dropped most vs their 14-day median."""
from datetime import date, timedelta

import streamlit as st

from bots.scouter import MIN_POINTS
from core import config, pricing, queries, ui

ui.chrome(config.NAV_DEALS)
queries.mark_alerts_seen(ui.conn())
ui.heading("Ascend deals from TPA", "Routes whose price dropped the most compared with their recent average.")

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
            res = pipeline.run_live_chain(params, ui.conn(), progress=status.update)
            status.update(label=f"{len(res['fares'])} nonstop flights found", state="complete")
        if res["error"]:
            st.warning(res["error"])
        with st.container(key="restable_deals"):
            for f in res["fares"]:
                ui.result_row(f, pricing.quote(f, carry, checked, party), scope="dealres")
else:
    window_id = queries.window_for_pill(window_label)
    items = ui.q("deals", window_id, trip_type, None if region == "All regions" else region)
    if not items:
        st.info("No fares for this window yet. Deals appear after the background scans run.")
    else:
        def render(d):
            ui.deal_card(d, pricing.card_price(d["fare"], carry, checked, party, bool(carry or checked)), "deals")

        ui.card_grid(items, render)
        opened = next((d["fare"] for d in items if d["fare"]["fare_id"] == st.session_state.get("open_deals")), None)
        if opened:
            ui.heading(f"Cabin experience · {ui.airline_label(opened)} to {config.city(opened['destination'])}", level=3)
            ui.cabin_panel(opened)
    st.markdown(f'<div class="credit" style="margin-top:1rem">Routes with fewer than {MIN_POINTS} price checks show '
                '“Tracking — trend available soon” instead of a % drop.</div>', unsafe_allow_html=True)

ui.footer()
