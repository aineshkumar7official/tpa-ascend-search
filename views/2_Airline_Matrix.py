"""Airline Matrix — Wireframes V5.1 p3 (grid) and p7–8 (detail, ?airline=XX)."""
import html

import streamlit as st

from core import config, ui
from sources import news

ui.chrome(config.NAV_MATRIX)
ui.scroll_to_top_if_asked()
code = (st.query_params.get("airline") or "").upper()

if code and code in config.airlines():
    info = config.airline(code)
    name = html.escape(info["name"])
    if st.button("← All airlines", type="tertiary", key="back_airlines"):
        del st.query_params["airline"]
        ui.open_at_top()
    left, right = st.columns([1, 1], gap="large")
    with left:
        ui.heading(name)
        if info.get("website"):
            st.markdown(f'<a class="linkish" href="{html.escape(info["website"])}" target="_blank">'
                        f'Visit {name} website ↗</a>', unsafe_allow_html=True)
        desc = config.airline_description(code)
        st.markdown(f'<div style="margin:.6rem 0">{html.escape(desc) if desc else "<span class=muted>Description coming soon.</span>"}</div>',
                    unsafe_allow_html=True)
        routes = ui.q("airline_routes", code)
        st.markdown(f"<b>{len(routes)} nonstop route{'s' if len(routes) != 1 else ''}</b> from TPA", unsafe_allow_html=True)
        one_way, round_trip = ui.q("airline_deals", code, "one_way"), ui.q("airline_deals", code, "round_trip")
        ui.fees_grid(code, one_way["cheapest_nonstop"] or round_trip["cheapest_nonstop"] or one_way["cheapest"] or round_trip["cheapest"])
        asset = ui.q("airline_photo_asset", code)
        ui.airline_cabin_card(code, asset)
        ui.airline_freebie(code)
    with right:
        ui.heading("Photo library", level=3)
        ui.photo_library(asset, code)
        # The One-way / Round-trip toggle sits further down the page; its value carries over from the last run.
        round_trip = st.session_state.get("airline_trip", "Round-trip") != "One-way"
        ui.routes_panel(code, routes, ui.q("route_prices", code, "round_trip" if round_trip else "one_way"), round_trip)

    st.write("")
    ui.news_panel(news.latest(ui.conn(), code))

    st.write("")
    head = st.columns([3, 1.2], vertical_alignment="center")
    with head[0]:
        ui.heading(f"Deals on {name} from TPA", level=2)
    with head[1], st.container(horizontal=True, horizontal_alignment="right"):
        trip = st.segmented_control("Trip type", ["One-way", "Round-trip"], default="Round-trip", key="airline_trip",
                                    label_visibility="collapsed") or "Round-trip"
    ui.deal_cards(code, ui.q("airline_deals", code, "round_trip" if trip == "Round-trip" else "one_way"))
else:
    if code:
        st.warning(f"Unknown airline code “{html.escape(code)}”.")
    ui.heading("Airline Matrix", "Every airline flying from TPA. Pick one to see its deals, cabin and what's included.")
    ui.card_grid(ui.q("matrix"), ui.airline_card, cols=4)

ui.footer()
