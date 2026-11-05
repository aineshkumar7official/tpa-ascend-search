"""TPA Ascend Search — entrypoint. Defines the top navigation and the Home view (Wireframes V4 p1, p10, p12).

    streamlit run app.py
"""
import streamlit as st

from core import config, pricing, ui

st.set_page_config(page_title=config.PRODUCT_NAME, page_icon="✈️", layout="wide",
                   initial_sidebar_state="collapsed")


def home():
    ui.chrome(config.NAV_HOME)
    ui.search_form()

    st.write("")
    head = st.columns([2.6, 1.4], vertical_alignment="bottom")
    with head[0]:
        scan = ui.q("latest_scan")
        updated = ui.local_time(scan["scanned_at"]).strftime("%b %-d, %-I:%M %p") if scan else "never"
        ui.heading("Cheapest nonstops out of TPA right now", f"Updated {updated} · prices may change", level=2)
    with head[1]:
        with st.container(horizontal=True, horizontal_alignment="right", key="hometoggles"):
            trip = st.segmented_control("Trip type", ["One-way", "Round-trip"], default="One-way",
                                        key="home_trip", label_visibility="collapsed") or "One-way"
            include_bags = bool(st.pills("Bags", ["Bags included"], key="home_bags",
                                         label_visibility="collapsed",
                                         help="Show prices with bags included (the bags you picked above, "
                                              "or 1 carry-on + 1 checked)"))
    trip_type = "round_trip" if trip == "Round-trip" else "one_way"
    party, carry, checked = ui.controls("home")  # cards follow the travelers/bags set in the form above
    if include_bags:
        # Re-rank by the total with bags: a cheap fare with high bag fees can lose to another airline.
        picks = pricing.cheapest_with_bags(ui.q("nonstop_candidates", trip_type), carry, checked, party)
    else:
        picks = [(f, pricing.card_price(f, carry, checked, party, False))
                 for f in ui.q("cheapest_nonstops", trip_type, 3)]
    fares = [f for f, _ in picks]
    if not fares and include_bags and ui.q("cheapest_nonstops", trip_type, 1):
        st.info("No bags-included prices yet: bag fees aren't verified for the airlines in the latest scan. "
                "Add them to `data/airline_policies.json` (see TODO_VERIFY.md), or turn off **Bags included**.")
    elif not fares:
        st.info("No prices yet — the first background scan fills this in "
                "(`python -m bots.pipeline --once`).")
    else:
        def render(item):
            i, (f, cp) = item
            ui.fare_card(f, cp, "home", highlight=(i == 0))

        ui.card_grid(list(enumerate(picks)), render)
        open_id = st.session_state.get("open_home")
        opened = next((f for f in fares if f["fare_id"] == open_id), None)
        if opened:
            ui.heading(f"Cabin experience · {ui.airline_label(opened)} to {config.city(opened['destination'])}", level=3)
            ui.cabin_panel(opened)
    ui.footer(full=True)


pages = {
    config.NAV_HOME: st.Page(home, title=config.NAV_HOME, default=True, url_path="home"),
    config.NAV_DEALS: st.Page("pages/1_Ascend_Deals.py", title=config.NAV_DEALS, url_path="ascend-deals"),
    config.NAV_MATRIX: st.Page("pages/2_Airline_Matrix.py", title=config.NAV_MATRIX, url_path="airline-matrix"),
    config.NAV_SEARCH: st.Page("pages/3_Ascend_Search.py", title=config.NAV_SEARCH, url_path="ascend-search"),
}
ui.PAGES.clear()
ui.PAGES.update(pages)
st.navigation(list(pages.values()), position="hidden").run()
