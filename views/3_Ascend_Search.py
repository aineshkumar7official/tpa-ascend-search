"""Ascend Search — wireframes V4 p4–5 (landing + To picker), p9 (one-way), p11 (round trip · separate legs),
p13 (round trip · bundles table), and p6, the Cabin experience view (?fare_id=...)."""
import streamlit as st

from bots import pipeline
from core import config, experience, pricing, queries, ui

ui.chrome(config.NAV_SEARCH)
ss = st.session_state
s = ui.search_state()
party = ui.party_of(s)


# ---------------------------------------------------------------- cached live calls (15 min)
def _params(s):
    return {"destination": s["destination"], "depart_date": s["depart_date"], "return_date": s.get("return_date"),
            "party": s["party"], "nonstop": s.get("nonstop", True)}


@st.cache_data(ttl=900, show_spinner=False)
def live_one(params):
    return pipeline.run_live_chain(dict(params), ui.conn())


def live(params):
    """Live search; an 'all airports' destination (V4) searches each airport and merges, cheapest first."""
    airports = config.metro_airports(params["destination"])
    if len(airports) == 1 and airports[0] == params["destination"]:
        return live_one(params)
    fares, sources, errors = [], [], []
    for code in airports:
        r = live_one({**params, "destination": code})
        fares += r["fares"]
        sources += [r["source"]] if r["source"] and r["source"] not in sources else []
        errors += [f"{code}: {r['error']}"] if r["error"] else []
    fares.sort(key=lambda f: f["price_usd"])
    error = None
    if errors:
        error = ("; ".join(errors)) if not fares else f"Some airports couldn't be searched ({'; '.join(errors)})."
    return {"fares": fares, "source": ", ".join(sources) or None, "error": error}


@st.cache_data(ttl=900, show_spinner=False)
def returns_for(params, outbound):
    return pipeline.run_return_chain(dict(params), dict(outbound), ui.conn())


@st.cache_data(ttl=900, show_spinner=False)
def bundles_for(params, outbounds):
    return pipeline.run_bundle_chain(dict(params), [dict(o) for o in outbounds], ui.conn())


def _lean(f):
    """Outbound fields needed to price its returns (keeps the cache key small and stable)."""
    keys = ("origin", "destination", "depart_date", "return_date", "flight_numbers", "via_airports", "segments",
            "airline_iata", "price_usd", "depart_time", "arrive_time", "duration_min", "aircraft_type", "fare_id",
            "stops", "search_url", "trip_type", "airline_name")
    return {k: f.get(k) for k in keys}


def _rehydrate(lean, full):
    """Swap lean outbound dicts back for the enriched ones (asset, amenities, review)."""
    by_id = {f["fare_id"]: f for f in full}
    return by_id.get(lean.get("fare_id"), lean)


def _change():
    ss["searched"] = False
    for k in [k for k in ss if k.startswith("land_")]:
        del ss[k]


# ---------------------------------------------------------------- Cabin experience view
fare_id = st.query_params.get("fare_id")
if fare_id:
    f = queries.fare_by_id(ui.conn(), fare_id)
    origin = st.query_params.get("from") or ""
    back = {"home": (config.NAV_HOME, "home", None), "deals": (config.NAV_DEALS, "deals", None)}.get(origin)
    if origin.startswith("airline:"):
        code = origin.split(":", 1)[1]
        back = (config.NAV_MATRIX, config.airline_name(code), {"airline": code})
    if st.button(f"← Back to {back[1]}" if back else "← Back to results", type="tertiary"):
        if back:
            st.switch_page(ui.PAGES[back[0]], query_params=back[2])
        del st.query_params["fare_id"]
        st.rerun()
    if not f:
        st.warning("That flight is no longer available. Search again for current prices.")
    else:
        ui.cabin_header(f, pricing.quote(f, s["carry_on"], s["checked"], f.get("party") or party))
        ui.booking_links(f)
        st.write("")
        ui.cabin_panel(f, compact=False)
    ui.footer()
    st.stop()

# ---------------------------------------------------------------- landing (p7)
if not ss.get("searched"):
    ui.heading("Ascend Search", "Pick how you want to fly, then search nonstop flights from Tampa.")
    ui.trip_form("land", with_modes=True)
    ui.footer()
    st.stop()

params = _params(s)
mode = s["mode"]


def show_airline_notice():
    if ui.airline_notice(s):
        s["airline"] = None
        st.rerun()
    note = ui.route_availability(s["destination"], s.get("airline"))
    if note:
        st.info(note, icon=":material/event_busy:")


# ---------------------------------------------------------------- one-way (p8)
if mode == "one_way":
    controls, update, change = ui.search_bar_compact(s)
    if change:
        _change()
        st.rerun()
    if update:
        s.update(controls)  # bags re-price; a party change re-runs the search (cache key includes party)
        st.rerun()
    show_airline_notice()
    with st.spinner("Searching live fares…"):
        res = live(params)
    res = {**res, "fares": ui.only_airline(res["fares"], s)}
    quotes = {f["fare_id"]: pricing.quote(f, s["carry_on"], s["checked"], party) for f in res["fares"]}
    fares = [f for f in res["fares"] if quotes[f["fare_id"]].bags_total is not None]  # picked bags need a known fee
    if res["error"]:
        st.warning(res["error"])
    head = st.columns([3, 1], vertical_alignment="center")
    kind = "nonstop flights" if s["nonstop"] else "flights"
    head[0].markdown(f'<div class="as-h2">{len(fares)} {kind} found</div>', unsafe_allow_html=True)
    with head[1]:
        sort = ui.inline_choice("Sort", ["Price", "Time"], "Price", "res_sort", st.pills)
    if sort == "Price":
        fares.sort(key=lambda f: quotes[f["fare_id"]].total)  # stable: ties keep source order
    else:
        fares.sort(key=lambda f: f.get("depart_time") or "99:99")
    if fares:
        with st.container(key="restable_main"):
            with st.container(key="rthead_main"):
                h = st.columns([0.6, 2.4, 2, 1.4, 1.6])
                for col, label in zip(h, ["Logo", "Route · airline", "Time", "Price", ""]):
                    col.markdown(f'<div class="rt-head">{label}</div>', unsafe_allow_html=True)
            for f in fares:
                ui.result_row(f, quotes[f["fare_id"]])
    ui.hidden_note(len(res["fares"]) - len(fares))
    if not fares or not s["nonstop"]:
        st.write("")
        st.markdown(f'<div class="muted">{"No nonstops for these dates?" if s["nonstop"] else "Showing flights with stops."}</div>',
                    unsafe_allow_html=True)
        include = st.toggle("Include flights with stops", value=not s["nonstop"])
        if include == s["nonstop"]:
            s["nonstop"] = not include
            st.rerun()
    ui.footer()
    st.stop()

# ---------------------------------------------------------------- round trip: shared top
if ui.search_bar_roundtrip(s):
    _change()
    st.rerun()

show_airline_notice()
with st.spinner("Searching live round-trip fares…"):
    res = live(params)
res = {**res, "fares": ui.only_airline(res["fares"], s)}
out_totals = pricing.leg_totals(res["fares"], s["carry_on"], s["checked"], party)
outbounds = [f for f in res["fares"] if f["fare_id"] in out_totals]  # picked bags need a known fee
hidden_outbounds = len(res["fares"]) - len(outbounds)
if res["error"]:
    st.warning(res["error"])
if not outbounds:
    ui.hidden_note(hidden_outbounds)
    st.markdown('<div class="muted">No nonstops for these dates?</div>', unsafe_allow_html=True)
    if st.toggle("Include flights with stops", value=not s["nonstop"]) == s["nonstop"]:
        s["nonstop"] = not s["nonstop"]
        st.rerun()
    ui.footer()
    st.stop()
city = config.city(s["destination"])

# ---------------------------------------------------------------- separate legs (p9)
if mode == "rt_legs":
    by_id = {f["fare_id"]: f for f in outbounds}
    if ss.get("sel_out") not in by_id:
        ss["sel_out"] = outbounds[0]["fare_id"]          # cheapest round trip by default
        ss.pop("sel_ret", None)
    out = by_id[ss["sel_out"]]
    left, right = st.columns([2.6, 1], gap="small")
    with left:
        ui.step_heading(1, "Choose your outbound",
                        f"TPA → {city} · {ui.nice_date(s['depart_date'])} · prices shown are the round-trip total",
                        "choose-outbound")
        for f in outbounds:
            ui.leg_row(f, out_totals[out["fare_id"]], f["fare_id"] == out["fare_id"], "sel_out", "out",
                       out_totals[f["fare_id"]], reset="sel_ret")
        ui.hidden_note(hidden_outbounds)
        st.write("")
        with st.spinner("Pricing return flights for your outbound…"):
            rres = returns_for(params, _lean(out))
        rres = {**rres, "fares": ui.only_airline(rres["fares"], s)}
        ret_totals = pricing.leg_totals(rres["fares"], s["carry_on"], s["checked"], party, out=out)
        rets = [r for r in rres["fares"] if r["fare_id"] in ret_totals]
        ret = None
        if rets:
            rby = {r["fare_id"]: r for r in rets}
            if ss.get("sel_ret") not in rby:
                ss["sel_ret"] = rets[0]["fare_id"]
            ret = rby[ss["sel_ret"]]
        ui.step_heading(2, "Choose your return", "Opens as a pop-up as soon as you pick an outbound flight", "choose-return")
        if rres["error"]:
            st.warning(rres["error"])
        ui.return_slot(out, ret, s)
        ui.hidden_note(len(rres["fares"]) - len(rets))
        if not rets and not rres["fares"] and not rres["error"]:
            st.markdown('<div class="muted">No nonstop returns with this outbound — pick another outbound.</div>',
                        unsafe_allow_html=True)
    with right:
        ui.roundtrip_summary(out, ret, s)
    if ss.pop("ret_dialog", False) and rets:
        ui.return_dialog(rets, ret, f"{config.city(out['destination'])} → TPA · {ui.nice_date(s['return_date'])} · "
                                    "prices shown are the round-trip total", ret_totals)
    ui.footer()
    st.stop()

# ---------------------------------------------------------------- bundles (p10)
picks = pipeline.bundle_outbounds(outbounds)
with st.spinner(f"Pricing complete round trips for {len(picks)} outbound flights…"):
    bres = bundles_for(params, [_lean(f) for f in picks])
if bres["error"]:
    st.warning(bres["error"])
bundles = pricing.bundles_with_bags([{**b, "out": _rehydrate(b["out"], outbounds)} for b in bres["bundles"]],
                                    s["carry_on"], s["checked"], party)
ui.hidden_note(hidden_outbounds)

head = st.columns([2.2, 2.4, 1.6], vertical_alignment="center")
with head[1]:
    sort = ui.inline_choice("Sort", list(experience.SORTS), "Best experience", "bundle_sort", st.pills)
mixed = head[2].checkbox("Allow different airlines each way", key="bundle_mixed")
ranked = experience.rank_bundles(bundles, allow_mixed=mixed)
ranked.sort(key=experience.SORTS[sort])
# The tagged bundles (Best experience / Lowest price / Shortest) always lead, in the chosen sort order.
ranked = [b for b in ranked if b["tags"]] + [b for b in ranked if not b["tags"]]
head[0].markdown(f'<div class="as-h2">{len(ranked)} round-trip bundles found</div>', unsafe_allow_html=True)

shown = ss.get("bundles_shown", 5)
if ranked:
    with st.container(key="restable_bundles"):
        ui.bundle_table_head()
        for i, b in enumerate(ranked[:shown]):
            ui.bundle_card(b, s, i)
if len(ranked) > shown and st.button(f"Show more bundles ({len(ranked) - shown} more)"):
    ss["bundles_shown"] = shown + 5
    st.rerun()
if ranked:
    st.markdown(f'<div class="credit" style="margin-top:.6rem">{experience.EXPLAINER} Bundles are built from the '
                f'{len(picks)} best outbound choices (one live request each).</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="muted">No same-airline round trips — try “Allow different airlines each way” or Separate legs.</div>',
                unsafe_allow_html=True)
ui.footer()
