"""Airline Matrix — Wireframes V5.1 p3 (grid) and p7–8 (detail, ?airline=XX)."""
import html

import streamlit as st

from bots.critic import pick_fun_fact
from core import config, ui
from sources import news

ui.chrome(config.NAV_MATRIX)
code = (st.query_params.get("airline") or "").upper()

if code and code in config.airlines():
    info = config.airline(code)
    name = html.escape(info["name"])
    if st.button("← All airlines", type="tertiary", key="back_airlines"):
        del st.query_params["airline"]
        st.rerun()
    left, right = st.columns([1, 1], gap="large")
    with left:
        ui.heading(name)
        if info.get("website"):
            st.markdown(f'<a class="linkish" href="{html.escape(info["website"])}" target="_blank">'
                        f'Visit {name} website ↗</a>', unsafe_allow_html=True)
        desc = info.get("description")
        st.markdown(f'<div style="margin:.6rem 0">{html.escape(desc) if desc else "<span class=muted>Description coming soon.</span>"}</div>',
                    unsafe_allow_html=True)
        routes = ui.q("airline_routes", code)
        st.markdown(f"<b>{len(routes)} nonstop route{'s' if len(routes) != 1 else ''}</b> from TPA", unsafe_allow_html=True)
        ui.fees_grid(code)
        fact = pick_fun_fact(code)
        with st.container(key=f"softcard_fact_{code}"):
            st.markdown(f'<div class="credit" style="margin:0">Fun fact</div><div>'
                        f'{html.escape(fact) if fact else "<span class=muted>Coming soon</span>"}</div>',
                        unsafe_allow_html=True)
    with right:
        ui.heading("Photo library", level=3)
        ui.photo_library(ui.q("airline_photo_asset", code))
        ui.routes_panel(code, routes, ui.q("route_prices", code))

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
