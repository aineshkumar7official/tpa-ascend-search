"""Airline Matrix — Wireframes V5.1 p3 (grid) and p7–8 (detail, ?airline=XX)."""
import html

import streamlit as st

from core import config, queries, ui
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
        ui.routes_panel(code, routes)  # has its own One-way / Round-trip toggle (V9.1)

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
    ui.heading("Airline Matrix", "Every airline flying from TPA. Filter by airline or destination type, then pick one "
               "to see its deals, cabin and what's included.")
    airlines = ui.q("matrix")
    with st.container(key="panel_filters"):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 0.55], gap="medium", vertical_alignment="bottom")
        sort = c1.selectbox("Sort", queries.MATRIX_SORTS, key="mx_sort")
        kind = c2.selectbox("Airline type", list(queries.AIRLINE_TYPES), key="mx_type")
        dest = c3.selectbox("Destination type", list(queries.DESTINATION_TYPES), key="mx_dest")
        shown = queries.filter_matrix(airlines, sort, kind, dest)
        regions = queries.destination_regions(dest)
        if regions:  # show the plane each airline flies to those destinations, when there's a trusted photo of it
            shown = [{**a, "asset": ui.q("route_cover", a["iata"], regions) or a["asset"],
                      "matching": queries.matching_routes(a["iata"], a["routes"], regions)} for a in shown]
        c4.markdown(f'<div class="mx-count">{len(shown)} of {len(airlines)} airlines</div>', unsafe_allow_html=True)
    st.write("")
    if shown:
        ui.card_grid(shown, ui.airline_card, cols=4)
    else:
        st.markdown('<div class="muted">No airlines match these filters.</div>', unsafe_allow_html=True)

ui.footer()
