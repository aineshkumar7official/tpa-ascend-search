"""Reusable page pieces. Pages only assemble these; all raw HTML lives here (CSS in theme.py)."""
import html
import unicodedata
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from core import booking, config, pricing, queries, remote_db, theme
from core.config import settings
from core.db import get_conn
from sources import fare_options

PAGES = {}  # nav label -> st.Page, filled by app.py every run before pg.run()
esc = html.escape


# Streamlit renders text between two "$" as LaTeX math, so a card showing "$84" and "$70–$120"
# turned into garbled italics with raw </div> tags. For raw-HTML markdown, swap "$" for its entity
# (still displays as "$", valid in text and attributes). Patched once, applies to every page.
if not getattr(st.markdown, "_dollar_safe", False):
    _st_markdown = st.markdown

    def _markdown(body, *args, unsafe_allow_html=False, **kwargs):
        if unsafe_allow_html and isinstance(body, str):
            body = body.replace("$", "&#36;")
        return _st_markdown(body, *args, unsafe_allow_html=unsafe_allow_html, **kwargs)

    _markdown._dollar_safe = True
    st.markdown = _markdown


# ================================================================ data access (cached)
def conn():
    """The shared connection for the database currently in use. Keyed by path: when the deployed app switches to a
    newer scan (core/remote_db.py) it gets a connection to that file, not one opened earlier on another database."""
    return _conn_for(settings.DB_PATH)


@st.cache_resource(max_entries=3)
def _conn_for(path):
    return get_conn(path)


@st.cache_data(ttl=300, show_spinner=False)
def q(name, *args):
    """Cached call of core.queries.<name>(conn, *args)."""
    return getattr(queries, name)(conn(), *args)


# ================================================================ formatting
def money(v):
    return f"${v:,.0f}" if v is not None else "—"


def hm(t):
    """'06:05' -> '6:05 AM'."""
    if not t:
        return "—"
    try:
        return datetime.strptime(t, "%H:%M").strftime("%-I:%M %p")
    except ValueError:
        return t


def duration(mins):
    if not mins:
        return "—"
    return f"{mins // 60}h {mins % 60:02d}m"


def nice_date(d):
    if not d:
        return ""
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%a, %b %-d")
    except ValueError:
        return str(d)


def dates_text(f):
    if f.get("return_date"):
        return f"{nice_date(f['depart_date'])} – {nice_date(f['return_date'])}"
    return nice_date(f.get("depart_date"))


def local_time(iso):
    if not iso:
        return None
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(settings.TIMEZONE))


def ago(iso):
    dt = local_time(iso)
    if not dt:
        return "never"
    mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if mins < 60:
        return f"{mins} min ago"
    if mins < 48 * 60:
        return f"{mins // 60} h ago"
    return dt.strftime("%b %-d, %-I:%M %p")


def book(f, return_fare=None):
    """Exact-fare Google Flights booking link, priced for the party the user picked."""
    s = st.session_state.get("search") or {}
    party = s.get("party") or f.get("party") or f.get("travelers") or 1
    return booking.book_url(f, party, return_fare or f.get("return_leg"))


def aircraft_label(f):
    t = f.get("aircraft_type")
    if not t:
        return ""
    return esc(t) + (' <span class="typical">Typical</span>' if f.get("aircraft_is_typical") else "")


def route_label(f):
    return f"TPA → {esc(config.city(f['destination']))}"


def stops_label(f):
    if not f.get("stops"):
        return "Nonstop"
    via = f.get("via_airports")
    n = f["stops"]
    return f"{n} stop{'s' if n > 1 else ''}" + (f" via {via}" if via else "")


def airline_label(f):
    return esc(config.airline_name(f.get("airline_iata")) if f.get("airline_iata") else (f.get("airline_name") or "Airline"))


# ================================================================ chrome
_db_seen = {"sha": None}


def sync_db():
    """Deployed app: use the database from the latest scan, and drop cached query results when it changes.
    Runs on every page load; remote_db only asks GitHub every 10 minutes."""
    config.refresh_settings()  # secrets saved in Streamlit Cloud apply without a reboot
    if not remote_db.enabled():
        return
    first = remote_db._state["path"] is None
    with st.spinner("Loading the latest prices…") if first else nullcontext():
        sha = remote_db.sync()
    if sha and (first or sha != _db_seen["sha"]):
        _db_seen["sha"] = sha
        q.clear()  # results cached before this database (e.g. from an empty one) are wrong now


def chrome(active):
    """Theme + header + nav row + banner. Call first on every page."""
    sync_db()
    theme.inject()
    st.markdown(
        f"""<div class="as-header bleed"><div class="as-brand"><img class="as-symbol" src="{config.HEADER_SYMBOL}" alt="">
        <span class="as-wordmark">{config.PRODUCT_NAME}</span></div>
        <div class="as-tagline">{config.TAGLINE}</div></div>""",
        unsafe_allow_html=True)
    alerts = queries.unseen_alerts(conn())  # uncached so the badge clears right after a Deals visit
    with st.container(horizontal=True, key="navrow"):
        for label in (config.NAV_HOME, config.NAV_DEALS, config.NAV_MATRIX, config.NAV_SEARCH):
            page = PAGES.get(label)
            if page is None:
                continue
            text = label
            if label == config.NAV_DEALS and alerts:
                text = f"{label} · {alerts} new"
            with st.container(key=f"navitem_active" if label == active else None, width="content"):
                st.page_link(page, label=text)
    st.markdown(f'<div class="as-banner bleed">{config.BANNER_LINE}</div>', unsafe_allow_html=True)


def footer(full=False):
    """Disclaimer strip on every page; the Explore / About / Data sources columns on Home only (wireframes V4 p1 vs p2-13).
    V11: maroon footer with the brand symbol on the left, white text and gold links."""
    symbol = f'<img class="as-footer-symbol" src="{config.HEADER_SYMBOL}" alt="">'
    if not full:
        st.markdown(f'<div class="as-footer short bleed"><div class="as-footer-row">{symbol}<div class="disc">'
                    f'Credentials / disclaimers: {config.DISCLAIMER_SHORT}</div></div></div>', unsafe_allow_html=True)
        return
    c = conn()
    serpapi = queries.serpapi_remaining(c) is not None
    links = {label: PAGES.get(label) for label in (config.NAV_DEALS, config.NAV_MATRIX, config.NAV_SEARCH)}
    paths = {label: (f"/{p.url_path}" if p is not None else "#") for label, p in links.items()}
    delay = ""
    if c.execute("SELECT 1 FROM delay_stats LIMIT 1").fetchone():
        delay = '<div>Delay data: U.S. DOT / BTS On-Time Performance</div>'
    html_ = f"""
<div class="as-footer bleed">
  <div class="as-footer-row">{symbol}
  <div class="cols">
    <div><h5>1. Explore</h5>
      {''.join(f'<div><a href="{paths[l]}" target="_self">{l}</a></div>' for l in paths)}
    </div>
    <div><h5>2. About</h5>
      <div>{config.PRODUCT_NAME} finds cheap nonstops out of Tampa (TPA) and shows what the flight is actually like: the plane, the cabin, the bags.</div>
    </div>
    <div><h5>3. Data sources</h5>
      <div>Fares: Google Flights (via fast-flights){' + SerpApi' if serpapi else ''}</div>
      <div>Photos: Planespotters.net photographers · Wikimedia Commons (credited on each image)</div>
      <div>Airports: OurAirports (public domain) · News: Google News RSS</div>
      {delay}
    </div>
  </div>
  </div>
  <div class="disc">Credentials / disclaimers: {config.DISCLAIMER} {config.STUDENT_LINE}</div>
</div>"""
    # Markdown treats indented lines after a blank line as code; flatten to one line per tag.
    st.markdown("".join(line.strip() for line in html_.splitlines()), unsafe_allow_html=True)


def heading(title, sub=None, level=1):
    cls = {1: "as-h1", 2: "as-h2", 3: "as-h3"}[level]
    st.markdown(f'<div class="{cls}">{title}</div>' + (f'<div class="as-sub">{sub}</div>' if sub else ""),
                unsafe_allow_html=True)


def stale_banner():
    """Shown when the newest scan is older than 2 intervals (scraper broken or scheduler off)."""
    last = queries.last_scan_time(conn())
    if not last:
        st.info("No scans yet. Run `python -m bots.pipeline --once` to collect the first prices.")
        return
    age_h = (datetime.now(timezone.utc) - local_time(last)).total_seconds() / 3600
    if age_h > 2 * settings.SCAN_INTERVAL_HOURS:
        st.warning(f"Showing the last good data — it is {age_h:.0f} hours old.")


# ================================================================ images + credits
def asset_src(url):
    """Local files are stored as "/app/static/...". On Streamlit Cloud the app runs under a "/~/+/" prefix, where that
    absolute path returns the app's HTML instead of the image; the relative "app/static/..." works there and locally."""
    return url[1:] if url and url.startswith("/app/static/") else url


def image(url, link=None, label="Photo", height=160, cls=""):
    url = asset_src(url)
    if not url:
        return f'<div class="img-ph {cls}" style="height:{height}px">[{esc(label)}]</div>'
    tag = f'<img class="img-tile {cls}" style="height:{height}px" src="{esc(url)}" alt="{esc(label)}" loading="lazy">'
    return f'<a href="{esc(link)}" target="_blank" rel="noopener">{tag}</a>' if link else tag


def credit(text, link=None):
    """'Photo: [photographer] / [source]' — always rendered next to images."""
    if not text:
        return ""
    full = text if text.lower().startswith(("photo", "©")) else f"Photo: {text}"
    body = esc(full)
    if link:
        body = f'<a href="{esc(link)}" target="_blank" rel="noopener">{body}</a>'
    return f'<div class="credit" title="{esc(full)}">{body}</div>'


def card_photo(a, height, cls="card-img"):
    """Card image with its required credit laid over the bottom edge, so the card body starts at the price (V4 p1).
    Rule: the whole plane shows, nose to tail. The photo is fitted inside the box (never cropped) and a blurred
    copy of it fills the space around it."""
    src = asset_src(a.get("exterior_url"))
    backdrop = f'<img class="card-img-bg" src="{esc(src)}" alt="" aria-hidden="true">' if src else ""
    return (f'<div class="card-photo">{backdrop}{image(a.get("exterior_url"), a.get("exterior_link"), "Plane photo · airline livery", height, cls)}'
            f'{credit(a.get("exterior_credit"), a.get("exterior_link"))}</div>')


def credits_block(pairs):
    seen, parts = set(), []
    for text, link in pairs:
        if text and text not in seen:
            seen.add(text)
            parts.append(credit(text, link))
    return "".join(parts)


# ================================================================ fare cards (Home + Deals)
def price_html(qt, size_cls="fc-price"):
    est = '<span class="est">est.</span>' if qt.is_estimate else ""
    return f'<span class="{size_cls}">{money(qt.total)}{est}</span>'


def fare_meta(f):
    return f"{dates_text(f)} · {hm(f.get('depart_time'))} – {hm(f.get('arrive_time'))} · {duration(f.get('duration_min'))}"


def carried_note(f):
    """'Price from the Nov 12 check.' for a fare kept from an earlier scan because the latest one missed its route."""
    at = local_time(f.get("carried_from"))
    return f"Price from the {at.strftime('%b %-d, %-I %p')} check." if at else None


def card_actions(f, key, came_from="home", note=None):
    """Book now + Cabin experience ▾ (V8 p4, p22). Inside a `cabin_panel_row()` block the panel opens full width
    below the card's row (see `row_cabin_panel`); elsewhere it opens inside the card as before.
    Everything sits in one group so the card's bottom alignment keeps the note under its buttons."""
    open_ = st.session_state.get(f"cxopen_{key}", False)
    carried = carried_note(f)
    note = " ".join(x for x in (carried, note) if x) or None
    with st.container(gap="small", key=f"actgroup_{key}"):
        with st.container(horizontal=True, gap="small", key=f"btnrow_{key}"):
            st.link_button("Book now", book(f), type="primary",
                           help="Opens Google Flights booking options for this exact flight")
            # The key changes while open so CSS can outline this button and its card (V8: the open card is gold).
            st.button(f"Cabin experience {'▴' if open_ else '▾'}", key=f"cxbtn{'on' if open_ else ''}_{key}",
                      on_click=_toggle_cabin, args=(key,))
        if note:
            st.markdown(f'<div class="credit" style="margin:0">{note}</div>', unsafe_allow_html=True)
        if not open_:
            return
        row = getattr(_ROW, "open", None)
        if row is not None:
            row.append((f, key, came_from))
            return
        with st.container(key=f"cxpanel_{key}", gap="small"):
            st.markdown(cabin_images_html(f.get("asset") or {}, 64) + cabin_facts_html(f, stacked=True),
                        unsafe_allow_html=True)
            _full_cabin_link(f, came_from)


_ROW = threading.local()  # per script run: the open Cabin experience panels of the card row being drawn


@contextmanager
def cabin_panel_row():
    """Cards drawn inside this block open their Cabin experience panel below the whole row, full width (V8 p4, p22)."""
    prev, _ROW.open = getattr(_ROW, "open", None), []
    try:
        yield
        opened = _ROW.open
    finally:
        _ROW.open = prev
    for f, key, came_from in opened:
        row_cabin_panel(f, key, came_from)


def _toggle_cabin(key):
    """One Cabin experience panel open at a time: opening one closes the rest."""
    was = st.session_state.get(f"cxopen_{key}", False)
    for k in [k for k in st.session_state if str(k).startswith("cxopen_")]:
        st.session_state[k] = False
    st.session_state[f"cxopen_{key}"] = not was


def _full_cabin_link(f, came_from):
    page = PAGES.get(config.NAV_SEARCH)
    if page is not None:
        st.page_link(page, label="Open full cabin experience ↗",
                     query_params={"fare_id": f["fare_id"], "from": came_from})


def row_cabin_panel(f, key, came_from):
    """'Cabin experience · [deal]' with Close ✕ (V8 p4, p22): cabin images, then baggage · food & drinks ·
    entertainment side by side, then the special freebie."""
    with st.container(key=f"cxrow_{key}", gap="small"):
        title, close = st.columns([6, 1], vertical_alignment="center")
        title.markdown(f'<span class="as-h3" style="margin:0">Cabin experience</span>'
                       f'<span class="cx-deal"> · {route_label(f)} · {airline_label(f)}</span>', unsafe_allow_html=True)
        with close, st.container(horizontal=True, horizontal_alignment="right"):
            st.button("Close ✕", key=f"cxclose_{key}", on_click=_toggle_cabin, args=(key,))
        st.markdown(cabin_images_html(f.get("asset") or {}, 190) + cabin_facts_html(f), unsafe_allow_html=True)
        _full_cabin_link(f, came_from)


def bags_chip(qt):
    included = qt.bags_chip().startswith("Price includes")
    return (f'<div class="bag-chip{" on" if included else ""}" title="{esc(qt.breakdown() or qt.note or "")}">'
            f'<span class="bag-chip-ico">{ICONS["checked"]}</span>{esc(qt.bags_chip())}</div>')


# ---------------------------------------------------------------- V3 card pieces
def google_fare(f, party=None, return_fare=None, wait=False):
    """What Google shows now for this flight (sources.fare_options), or None. Cards never wait on the browser:
    they queue the lookup and use it on the next rerun. `wait` looks it up now, for panels the user just opened."""
    party = party or party_of()
    ret = return_fare or f.get("return_leg")
    hit, data = fare_options.cached(conn(), f, party, ret)
    if hit:
        return data
    if not wait:
        fare_options.enqueue(f, party, ret)
        return None
    if not (fare_options.available() and fare_options.lookable(f, ret)):
        return None
    with st.spinner("Checking this fare on Google Flights…"):
        return fare_options.lookup(conn(), f, party, ret)


def card_price(f, party, carry, checked, include_bags):
    return pricing.card_price(f, carry, checked, party, include_bags, google=google_fare(f, party))


def home_picks(trip_type, party, carry, checked, include_bags):
    """The Home cards: [(fare, CardPrice)], cheapest first, no airline or city repeated. With bags included they are
    re-ranked by the with-bags total (a cheap fare with high bag fees can lose to another airline)."""
    if include_bags:
        return [(f, card_price(f, party, carry, checked, True))
                for f, _ in pricing.cheapest_with_bags(q("nonstop_candidates", trip_type), carry, checked, party)]
    return [(f, card_price(f, party, carry, checked, False)) for f in q("cheapest_mix", trip_type, 3)]


def _checked_at(data):
    at = local_time((data or {}).get("checked_at"))
    return at.strftime("%b %-d, %-I:%M %p") if at else ""


def _changes(lines):
    return f'<div class="up-sub">{esc(" · ".join(lines))}</div>' if lines else ""


def fare_ladder(data):
    """'This price' plus each dearer fare Google lists for this flight. Rows show only their own add-on cost (V6 p15)."""
    base = fare_options.cheapest(data)
    if not base:
        return ""
    rows = [f'<div class="up-row"><span>This price: <b>{esc(base["name"])}</b></span><span><b>{money(base["price"])}</b></span></div>'
            + _changes(base["lines"])]
    for u in fare_options.upgrades(data):
        rows.append(f'<div class="up-row"><span>{esc(u["name"])}</span><span>+{money(u["extra"])}</span></div>'
                    + _changes(u["changes"]))
    return "".join(rows)


def fare_source_note(data, short=False):
    """Where the numbers came from, and how far to trust them. `short` is for the small box on a card."""
    if short:
        return (f"From Google Flights, checked {_checked_at(data)}." if fare_options.cheapest(data)
                else "Fees are the airline's published ones.")
    if fare_options.cheapest(data):
        return f"From Google Flights for this exact flight, checked {_checked_at(data)}. Confirm on the booking page."
    if fare_options.price(data):
        return (f"Google Flights lists one price for this flight, checked {_checked_at(data)}, with no fare options. "
                "Other fees are this airline's published ones. Confirm on the booking page.")
    return "Airline-wide published fees, not specific to this flight. Confirm on the booking page."


def _unit(f):
    return "round trip" if f.get("trip_type") == "round_trip" else "one-way"


def headline_html(cp, after, added=0):
    """'[$Price] one-way' / '[$Price] was ~[$Avg]' — price first (V3). Ticked upgrades raise it: '↑ +$35' (V6 p15)."""
    est = '<span class="est">est.</span>' if cp.is_estimate else ""
    up = f'<span class="v3-up">↑ +{money(added)}</span>' if added else ""
    return (f'<div class="v3-price"><span class="fc-price">{money(cp.headline + added)}{est}</span>'
            f'<span class="v3-unit">{after}</span>{up}</div>')


def legs_html(f):
    """One line for one-way; Depart/Return rows for round trips (V3 p12). The scan looks up the return for each
    airline's cheapest fare; any other fare shows its return date and leaves the times to the booking page."""
    times = f"{hm(f.get('depart_time'))} – {hm(f.get('arrive_time'))} · {duration(f.get('duration_min'))}"
    if f.get("trip_type") != "round_trip" or not f.get("return_date"):
        return f'<div class="fc-meta">{nice_date(f.get("depart_date"))} · {times}</div>'
    ret = f.get("return_leg")
    if ret:
        ret_times = f"{hm(ret.get('depart_time'))} – {hm(ret.get('arrive_time'))} · {duration(ret.get('duration_min'))}"
        if ret.get("airline_iata") != f.get("airline_iata") and ret.get("airline_name"):
            ret_times += f" · {esc(ret['airline_name'])}"  # the card's airline line describes the outbound
    else:
        ret_times = '<span class="muted">times on booking page</span>'
    return (f'<div class="v3-legs"><span class="v3-leg">Depart</span><span>{nice_date(f.get("depart_date"))} · {times}</span>'
            f'<span class="v3-leg">Return</span><span>{nice_date(f.get("return_date"))} · {ret_times}</span></div>')


def card_text(f, cp, after, route_tag="", added=0):
    return (headline_html(cp, after, added)
            + f'<div class="v3-route"><span class="fc-route">{route_label(f)}</span>{route_tag}</div>'
            + legs_html(f)
            + f'<div class="fc-line">{airline_label(f)} · {stops_label(f)}{" · " + aircraft_label(f) if f.get("aircraft_type") else ""}</div>')


def _upgrade_rows(f, cp):
    return pricing.upgrade_rows(f, cp, party_of(), pricing.google_policies(f.get("airline_iata"), google_fare(f)))


def _picked(key):
    return st.session_state.get("upgrades", {}).get(key, frozenset())


def card_added(f, cp, key):
    """What this card's ticked upgrades add to its price."""
    return pricing.upgrades_added(_upgrade_rows(f, cp), _picked(key))


def _set_upgrade(key, row_id, widget):
    """Ticks live outside the widgets, so closing the list doesn't drop them from the price."""
    store = st.session_state.setdefault("upgrades", {})
    picked = set(store.get(key, ()))
    (picked.add if st.session_state[widget] else picked.discard)(row_id)
    store[key] = frozenset(picked)


def _toggle_upgrades(key):
    st.session_state[f"upopen_{key}"] = not st.session_state.get(f"upopen_{key}")


def _upgrade_row(r, key, picked):
    """A tickable +$X row, or a fixed one: green tick 'Included', or an empty box with what we know instead."""
    if r["fee"]:
        widget = f"upg_{key}_{r['id']}"
        on = r["id"] in picked
        with st.container(horizontal=True, key=f"uprow_{key}_{r['id']}", vertical_alignment="center", gap="small"):
            st.checkbox(f"**{r['label']}**" if on else r["label"], value=on, key=widget, on_change=_set_upgrade,
                        args=(key, r["id"], widget))
            st.markdown(f'<div class="up-val">+{money(r["fee"])}</div>', unsafe_allow_html=True)
    elif r["included"]:
        st.markdown(f'<div class="up-line"><span class="up-box in">✓</span><span class="up-lbl muted">{esc(r["label"])}</span>'
                    '<span class="up-val in">Included</span></div>', unsafe_allow_html=True)
    else:
        # Can't change the price (a range, "from", or no amount): no checkbox, just what we know (V7 p5, state 5).
        st.markdown(f'<div class="up-line"><span class="up-box none" aria-hidden="true"></span><span class="up-lbl">{esc(r["label"])}</span>'
                    f'<span class="up-val">{esc(r["note"])}</span></div>', unsafe_allow_html=True)


def fare_body(f, cp, key):
    """Inside Fare & upgrades (V7 p5): Base fare, the UPGRADES rows, then Your price = base fare + ticked upgrades."""
    rows, picked = _upgrade_rows(f, cp), _picked(key)
    added = pricing.upgrades_added(rows, picked)
    st.markdown(f'<div class="up-line up-base"><span class="up-lbl">Base fare</span><span class="up-val">{money(cp.headline)}</span></div>'
                '<div class="up-sec">Upgrades</div>', unsafe_allow_html=True)
    for r in rows:
        _upgrade_row(r, key, picked)
    data = google_fare(f)
    if added:
        hint = "Your price = base fare + selected upgrades."
    elif not (cp.bag_known or any(r["fee"] or r["included"] for r in rows)):
        hint = "Book now opens Google Flights, which shows final bag fees."
    else:
        hint = ("The price updates as you choose upgrades." if any(r["fee"] for r in rows)
                else "Exact upgrade prices show on Google Flights when you book.")
        if cp.bag_level != "unknown":
            hint += f" This fare: {cp.bags_line()[0].lower()}{cp.bags_line()[1:]}."
    ladder = fare_ladder(data)
    more = (f'<details class="fare-more"><summary>Other fares on this flight ({len(data["options"]) - 1})</summary>{ladder}</details>'
            if ladder and len(data["options"]) > 1 else "")
    st.markdown(f'<div class="up-total"><span>Your price</span><span>{money(cp.headline + added)}</span></div>'
                f'<div class="up-hint">{hint}</div>{more}<div class="credit">{esc(fare_source_note(data, short=True))}</div>',
                unsafe_allow_html=True)


def bags_line(f, cp, key):
    """The bag tag (V7 p5): which bags the fare includes (checked bag, carry-on, personal item only, none), what the
    price includes when bags were picked, '1 checked bag added' or 'Bag info unavailable'."""
    rows, picked = _upgrade_rows(f, cp), _picked(key)
    added_bag = any(r["id"] == "checked" and r["fee"] and r["id"] in picked for r in rows)
    state = "checked" if added_bag else cp.bag_level  # each allowance has its own color (theme.py .bag-chip.v3.*)
    return (f'<div class="bag-chip v3 {state}" title="{esc(cp.tooltip(money))}">'
            f'<span class="bag-chip-ico">{ICONS["checked"]}</span><span>{esc(cp.bags_line(added_bag))}</span></div>')


def bags_row(f, cp, key):
    """Fare & upgrades box (V7 p1, p5): the bag tag + 'Fare & upgrades ▾', opening to rows that change the card's price."""
    open_ = st.session_state.get(f"upopen_{key}", False)
    with st.container(key=f"faresbox_{key}", gap="small"):
        with st.container(horizontal=True, key=f"baghead_{key}", vertical_alignment="center", gap="small"):
            st.markdown(bags_line(f, cp, key), unsafe_allow_html=True)
            st.button(f"Fare & upgrades {'▴' if open_ else '▾'}", key=f"upbtn_{key}", type="tertiary",
                      on_click=_toggle_upgrades, args=(key,))
        if open_:
            fare_body(f, cp, key)


def _flip(state_key):
    st.session_state[state_key] = not st.session_state.get(state_key)


def fare_card(f, cp, scope, highlight=False):
    """Home card (V3 p1/p12)."""
    a = f.get("asset") or {}
    key = f"{'cardhl' if highlight else 'card'}_{scope}_{f['fare_id']}"
    row_key = f"{scope}_{f['fare_id']}"
    with st.container(key=key):
        st.markdown(
            card_photo(a, 135) + f'<div class="card-body">{card_text(f, cp, _unit(f), added=card_added(f, cp, row_key))}</div>',
            unsafe_allow_html=True)
        bags_row(f, cp, row_key)
        card_actions(f, row_key, "home")


# ---------------------------------------------------------------- V3 price trend (Deals + Airline trending)
def daily_points(points, scale=1.0):
    """[(scanned_at, price)] -> [(local date, lowest price that day × scale)], oldest first."""
    by_day = {}
    for at, p in points:
        dt = local_time(at)
        d = dt.date() if dt else None
        if d and (d not in by_day or p < by_day[d]):
            by_day[d] = p
    return [(d, by_day[d] * scale) for d in sorted(by_day)]


def _day(d):
    return d.strftime("%b %-d")


def _delta_html(prev, cur):
    if prev is None:
        return '<div class="tc-delta flat">First price check</div>'
    diff = cur - prev
    if round(diff) == 0:
        return '<div class="tc-delta flat">No change vs. day before</div>'
    pct = round(diff / prev * 100) if prev else 0
    cls, arrow = ("down", "▼") if diff < 0 else ("up", "▲")
    return f'<div class="tc-delta {cls}">{arrow} {money(abs(diff))} vs. day before ({pct:+d}%)</div>'


def _spark_mini(vals, w=64, h=18):
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{(h / 2 if hi == lo else h - 2 - (v - lo) / (hi - lo) * (h - 4)):.1f}"
                   for i, v in enumerate(vals))
    return (f'<svg class="tr-mini" viewBox="0 0 {w} {h}" width="{w}" height="{h}" preserveAspectRatio="none">'
            f'<polyline fill="none" stroke="{theme.TOKENS["maroon"]}" stroke-width="1.6" points="{pts}"/></svg>')


def trend_chart(days, avg=None, w=700, h=240):
    """Daily-price line chart. Hover/tap any day for '[Date] · [$Price]' and the change vs. the day before
    (pure HTML/CSS, so it needs no rerun)."""
    if len(days) < 2:
        return '<div class="spark-empty">Daily prices appear after two days of price checks.</div>'
    vals = [p for _, p in days]
    lo, hi = min(vals), max(vals)
    pad = 8
    step = (w - 2 * pad) / (len(days) - 1)

    def x(i):
        return pad + i * step

    def y(v):
        return h / 2 if hi == lo else pad + (hi - v) / (hi - lo) * (h - 2 * pad)

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    avg_line = ""
    if avg is not None and lo <= avg <= hi and hi != lo:
        avg_line = (f'<line x1="0" x2="{w}" y1="{y(avg):.1f}" y2="{y(avg):.1f}" stroke="{theme.TOKENS["border"]}" '
                    f'stroke-width="1" vector-effect="non-scaling-stroke"/>')
    svg = (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">{avg_line}'
           f'<polyline fill="none" stroke="{theme.TOKENS["maroon"]}" stroke-width="2" vector-effect="non-scaling-stroke" points="{pts}"/>'
           f'<line class="tc-last" x1="{x(len(vals) - 1):.1f}" x2="{x(len(vals) - 1):.1f}" y1="0" y2="{h}" '
           f'stroke="{theme.TOKENS["maroon"]}" stroke-width="1" vector-effect="non-scaling-stroke"/></svg>')

    def label(i):
        d, p = days[i]
        return (f'<div class="tc-cur"><b>{_day(d)} · {money(p)}</b>'
                f'{_delta_html(days[i - 1][1] if i else None, p)}</div>')

    hits = "".join(
        f'<div class="tc-hit"><div class="tc-lbl">{label(i)}</div>'
        f'<div class="tc-vl" style="left:{x(i) / w * 100:.2f}%"></div>'
        f'<div class="tc-dot" style="left:{x(i) / w * 100:.2f}%;top:{y(v) / h * 100:.2f}%"></div></div>'
        for i, v in enumerate(vals))
    last = len(vals) - 1
    y_axis = "".join(f"<span>{money(v)}</span>" for v in ((hi, (hi + lo) / 2, lo) if hi != lo else (hi,)))
    return (f'<div class="tc">{label(last)}<div class="tc-grid"><div class="tc-y">{y_axis}</div>'
            f'<div class="tc-plot">{svg}<div class="tc-dot tc-last" style="left:{x(last) / w * 100:.2f}%;'
            f'top:{y(vals[last]) / h * 100:.2f}%"></div><div class="tc-hits">{hits}</div></div></div>'
            f'<div class="tc-axis"><span>{_day(days[0][0])}</span><span>{_day(days[-1][0])}</span></div></div>')


def _drop_text(d, label):
    if d["tracking"]:
        return '<span class="tr-pct flat">Tracking — trend available soon</span>'
    pct = round((d["drop_pct"] or 0) * 100)
    cls = "down" if pct > 0 else ("up" if pct < 0 else "flat")
    arrow = "▼" if pct > 0 else ("▲" if pct < 0 else "–")
    return f'<span class="tr-pct {cls}">{arrow} {abs(pct)}% {label}</span>'


def _span_label(days):
    """'over 5 days' from the actual price checks: a trend only covers its one departure date, so often < 14 days."""
    n = (days[-1][0] - days[0][0]).days if days else 0
    return f"over {n} day{'s' if n != 1 else ''}" if n else "today"


def _days_within(days, n):
    return [(dt, p) for dt, p in days if (days[-1][0] - dt).days < n]


def trend_strip(d, f, key, scale=1.0):
    """Deal card trend box (V7 p4): mini sparkline + '▼ X% over N days' + ▾, opening the daily-price chart in the card."""
    days = daily_points(d.get("points") or [], scale)
    shown = _days_within(days, 14)
    open_ = bool(days) and st.session_state.get(f"tropen_{key}", False)
    sub = "Price trend · tap or hover for daily prices" if days else "Price checks start with the next scan"
    with st.container(key=f"trendbox_{key}", gap="small"):
        with st.container(horizontal=True, key=f"trendrow_{key}", vertical_alignment="center", gap="small"):
            st.markdown(f'<div class="tr-sum static">{_spark_mini([p for _, p in shown])}<span class="tr-txt">'
                        f'{_drop_text(d, _span_label(days))}<span class="tr-hint">{sub}</span></span></div>',
                        unsafe_allow_html=True)
            if days:
                st.button("▴" if open_ else "▾", key=f"trendbtn_{key}", type="tertiary", on_click=_flip,
                          args=(f"tropen_{key}",), help="Show daily prices")
        if open_:
            vals = [p for _, p in shown]
            st.markdown(trend_chart(shown, d["baseline"] * scale if d.get("baseline") else None, w=320, h=110)
                        + f'<div class="tr-lohi">Low {money(min(vals))} · High {money(max(vals))}</div>',
                        unsafe_allow_html=True)


def trend_summary(days):
    """Price summary tiles for the pop-up (V6 p9). 'Today' only when the latest price check really was today."""
    vals = [p for _, p in days]
    latest, avg = days[-1], sum(vals) / len(vals)
    low, high = min(days, key=lambda x: x[1]), max(days, key=lambda x: x[1])
    today = local_time(datetime.now(timezone.utc).isoformat()).date()
    span = (latest[0] - days[0][0]).days + 1
    tiles = [("Today" if latest[0] == today else f"Latest · {_day(latest[0])}", money(latest[1]), ""),
             (f"{span}-day average", money(avg), ""),
             (f"Lowest · {_day(low[0])}", money(low[1]), "down"),
             (f"Highest · {_day(high[0])}", money(high[1]), "")]
    pct = round((latest[1] - avg) / avg * 100) if avg else 0
    cls, arrow = ("down", "▼") if pct < 0 else (("up", "▲") if pct > 0 else ("flat", "–"))
    return ('<div class="ts-grid">' + "".join(f'<div class="ts-tile"><div class="k">{k}</div><div class="v {c}">{v}</div></div>'
                                              for k, v, c in tiles) + "</div>"
            f'<div class="tr-pct {cls}" style="margin-top:.5rem">{arrow} {abs(pct)}% vs. {span}-day avg</div>')


_STANDOUT_BASIS = {  # standout basis -> (short note on the card, tooltip)
    "typical": ("vs. typical", "At least 10% and $20 below this route's typical price for the same departure date"),
    "early": ("vs. earlier checks", "At least 10% and $20 below this route's earlier prices for the same departure date "
                                    "(only a few checks so far)"),
    "last": ("since last check", "At least 10% and $20 below the previous price check for the same departure date"),
}


def _standout_badge(d):
    hit = d["standout"]
    note, tip = _STANDOUT_BASIS[hit["basis"]]
    return (f'<div class="mod-top"><span class="btag tag-low" title="{esc(tip)}">▼ {round(hit["pct"] * 100)}% · '
            f'Stand-out deal</span><span class="mod-note">{esc(d["window_label"])} · {note}</span></div>')


def deal_card(d, cp, scope):
    """Ascend Deals card (V7 p4): '$Price was ~$Avg', then Fare & upgrades, Cabin experience and Price trend dropdowns.
    Stand-out deals (they carry window_label and standout) get a badge saying how far the price fell and which date window it's from."""
    f, a = d["fare"], d["fare"].get("asset") or {}
    after = _unit(f)  # until the route has a baseline, just say one-way / round trip
    # A stand-out's "was" is the price its badge compares against; otherwise the route's typical price.
    ref = d["standout"]["ref"] if d.get("standout") else (d.get("baseline") if not d["tracking"] else None)
    if ref:
        # Same basis as the headline: fare-only reference, plus the same bag estimate when bags are included.
        was = ref * cp.travelers + (cp.headline - cp.fare_total)
        after = f"was ~{money(was)}"
    row_key = f"{scope}_{f['fare_id']}"
    with st.container(key=f"card_{scope}_{f['fare_id']}"):
        st.markdown(
            card_photo(a, 125) + f'<div class="card-body">{_standout_badge(d) if d.get("standout") else ""}'
            f'{card_text(f, cp, after, added=card_added(f, cp, row_key))}</div>',
            unsafe_allow_html=True)
        bags_row(f, cp, row_key)
        trend_strip(d, f, row_key, scale=cp.travelers)
        card_actions(f, row_key, "deals")



def card_grid(items, render, cols=3):
    for i in range(0, len(items), cols):
        with cabin_panel_row():
            row = st.columns(cols, gap="medium")
            for col, item in zip(row, items[i:i + cols]):
                with col:
                    render(item)


# ================================================================ cabin experience
_CHIP_SVG = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round">{}</svg>')
CHIP_ICONS = {
    "wifi": (_CHIP_SVG.format('<path d="M2 9a16 16 0 0 1 20 0"/><path d="M5.5 13a11 11 0 0 1 13 0"/>'
                              '<path d="M9 16.5a5.5 5.5 0 0 1 6 0"/><path d="M12 20h.01"/>'), "Wi-Fi"),
    "seatback_screen": (_CHIP_SVG.format('<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>'),
                        "Seatback screen"),
    "stream_to_device": (_CHIP_SVG.format('<rect x="7" y="2" width="10" height="20" rx="2"/><path d="m11 9 3 3-3 3z"/>'),
                         "Stream to your device"),
    "power": (_CHIP_SVG.format('<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>'), "Power"),
}


# What each chip's pop-up lists (V7 p20). amenities.json keys; a missing value says "Not verified yet".
CHIP_DETAILS = {
    "wifi": (("Cost", "wifi_cost"),),  # speed isn't shown: not needed (wifi_speed stays in amenities.json)
    "seatback_screen": (("Screen size", "screen_size_in"), ("Entertainment system", "entertainment_system")),
    "stream_to_device": (("App", "stream_app"), ("How to connect", "stream_connect"), ("What's on", "stream_content")),
    "power": (("Outlet type", "power_outlet"),),
}


def _chip_pop(key, amen):
    rows = []
    fields = CHIP_DETAILS[key]
    if key == "stream_to_device" and any(amen.get(f) for _, f in fields):
        fields = [(label, f) for label, f in fields if amen.get(f)]  # e.g. Alaska: just the app's name, no "Not verified" rows
    for label, field in fields:
        v = amen.get(field)
        if v and field == "screen_size_in":
            v = f"{v} in"
        rows.append(f'<span class="k">{label}</span>'
                    + (f'<span class="v">{esc(str(v))}</span>' if v else '<span class="v unknown">Not verified yet</span>'))
    return f'<span class="chip-pop" role="tooltip">{"".join(rows)}</span>'


def amenity_chips(amen):
    """Chips only for amenities that are true; hovering (or tapping) one shows its details (V7 p20).
    Missing/false keys render nothing."""
    amen = amen or {}
    return "".join(f'<span class="chip ent" tabindex="0">{icon} {label}{_chip_pop(k, amen)}</span>'
                   for k, (icon, label) in CHIP_ICONS.items() if amen.get(k) is True)


NO_AMENITIES = "No Wi-Fi, screens or power"


def has_no_amenities(amen):
    """True only when all four are verified false; missing/null stays 'not verified'."""
    return all((amen or {}).get(k) is False for k in CHIP_ICONS)


def entertainment_html(amen):
    """Chips for what's on board, a plain 'none' when verified absent, otherwise 'not verified'."""
    return amenity_chips(amen) or _amen_value(NO_AMENITIES if has_no_amenities(amen) else None)


def _amen_value(v, unknown="Not verified yet"):
    return f'<div class="v">{esc(str(v))}</div>' if v else f'<div class="v unknown">{unknown}</div>'


CABIN_SLOTS = (("exterior", "The plane"), ("seat", "Seats"), ("food", "Food/drink"))


def _slot(a, k):
    """(url, link, credit) for one cabin image. Seats fall back to the cabin photo when there's no seat photo."""
    if k == "seat" and not a.get("seat_url"):
        k = "interior"
    return a.get(f"{k}_url"), a.get(f"{k}_link"), a.get(f"{k}_credit")


def cabin_images_html(a, height=110):
    """'Cabin images' (V7.2): The plane · Seats · Food/drink side by side, with their credits."""
    slots = [(_slot(a, k), label) for k, label in CABIN_SLOTS]
    tiles = "".join(f'<div>{image(u, l, label, height)}</div>' for (u, l, _), label in slots)
    return (f'<div class="cx-imgs-h">Cabin images</div><div class="cx-imgs">{tiles}</div>'
            + credits_block([(c, l) for (_, l, c), _ in slots]))


def reviews_line(r, f=None):
    """'[★ X.X / 5] · [N] reviews ([route / airline-wide])' with the matched level spelled out."""
    airline = config.airline_name((f or {}).get("airline_iata")) if f else None
    if not r or r.get("match_level") == "none" or not r.get("review_count"):
        return '<div class="muted">No reviews yet</div>'
    stars = f'<span class="stars">★ {r["stars_5"]:.1f} / 5</span>' if r.get("stars_5") is not None else ""
    if r["match_level"] == "route" and f:
        scope = f"Reviews for TPA ⇄ {esc(f['destination'])} on {esc(airline)} ({r['review_count']})"
    else:
        scope = f"General {esc(airline or '')} economy reviews ({r['review_count']}) · airline-wide".replace("General  ", "General ")
    lines = [f"{stars} · {scope}" if stars else scope]
    lines.append(" · ".join(x for x in (r.get("highlight_pros"), r.get("highlight_cons")) if x) or "")
    return "".join(f"<div>{line}</div>" for line in lines if line)


def typical_tag(f):
    return (f'<span class="typical">Typical for {esc(config.airline_name(f.get("airline_iata")))}</span>'
            if f.get("amenities_typical") else "")


def freebie_lines(cool, fact):
    """Freebie, then fun fact. Most facts restate the freebie ('Trading cards' / 'Delta offers trading cards'): show it once."""
    perk = (cool or "").lower().removeprefix("free ")
    return [x for x in (cool, None if fact and perk and perk in fact.lower() else fact) if x]


def _carry_text(amen, data):
    """This fare's carry-on rule from Google when it says, otherwise the airline-wide one."""
    lines = fare_options.rules(fare_options.cheapest(data), "carry-on")
    return lines[0] if lines else amen.get("carry_on")


def _checked_text(f, amen, data):
    """'[$ fee · weight limit]' for the first checked bag: Google's fee for this fare, else the airline's published one."""
    item = (config.policies().get(f.get("airline_iata") or "") or {}).get("first_checked") or {}
    base = fare_options.cheapest(data) or {}
    fee = base.get("first_bag") if base.get("first_bag") is not None else item.get("fee_usd")
    text = ("Free" if fee == 0 else money(fee)) if fee is not None else item.get("fee_label")
    weight = amen.get("checked_weight") or item.get("weight_limit")
    return " · ".join(str(x) for x in (text, weight) if x) or None


def _unknown(v):
    return esc(str(v)) if v else '<span class="unknown">Not verified yet</span>'


def legroom_text(amen):
    """'Seat pitch · 31 in' from the airline's published economy seat pitch (V10), or None when unknown."""
    pitch = str((amen or {}).get("legroom_pitch_in") or "").strip()
    return f"Seat pitch · {pitch} in" if pitch else None


def cabin_facts_html(f, stacked=False, data=None, cols=4):
    """Baggage · Food & drinks · Entertainment (hover a chip) · Legroom, then Special freebie when the airline has one
    (V7 p3, p20; Legroom V10). `stacked` is the narrow 2×2 version inside a card's Cabin experience dropdown; `cols`
    is the column count otherwise (the airline page uses 3, so Legroom wraps under Baggage)."""
    amen = f.get("amenities") or {}
    data = google_fare(f) if data is None else data
    chips = amenity_chips(amen)
    ent_k = "Entertainment · <i>hover a chip</i>" if chips else "Entertainment"
    ent = chips or _amen_value(NO_AMENITIES if has_no_amenities(amen) else None)
    cells = (f'<div class="amen"><div class="k">Baggage</div><div class="v">Carry-on · {_unknown(_carry_text(amen, data))}</div>'
             f'<div class="v">Checked · {_unknown(_checked_text(f, amen, data))}</div></div>'
             f'<div class="amen"><div class="k">Food &amp; drinks</div><div class="v">{_unknown(amen.get("food_drinks"))}</div></div>'
             f'<div class="amen amen-ent"><div class="k">{ent_k}</div>{ent}</div>'
             f'<div class="amen"><div class="k">Legroom</div><div class="v">{_unknown(legroom_text(amen))}</div></div>')
    cool = amen.get("cool_thing")
    free = (f'<div class="freebie-box"><div class="k">Special freebie</div><div class="v">{esc(cool)}</div></div>'
            if cool else "")
    tag = f'<div class="cx-typical">{typical_tag(f)}</div>' if f.get("amenities_typical") else ""
    layout = " stacked" if stacked else ("" if cols == 4 else f" cols{cols}")
    return f'<div class="cx-grid{layout}">{cells}</div>{free}{tag}'


def cabin_panel(f, compact=True, came_from=None):
    """Cabin experience (V7 p3): cabin images; baggage, food & entertainment; special freebie.
    compact=True is the panel that opens under a result row; compact=False is the standalone view body.
    `came_from` ("home") tells the full view where its back button should go; without it, back to search results."""
    a = f.get("asset") or {}
    data = google_fare(f, wait=True)
    if compact:
        with st.container(key=f"cabinpanel_{f['fare_id']}"):
            st.markdown(cabin_images_html(a, 130) + cabin_facts_html(f, data=data), unsafe_allow_html=True)
            page = PAGES.get(config.NAV_SEARCH)
            if page is not None:
                params = {"fare_id": f["fare_id"], **({"from": came_from} if came_from else {})}
                st.page_link(page, label="Open full cabin experience ↗", query_params=params)
        return
    heading("Cabin experience", level=2)
    st.markdown(cabin_images_html(a, 150).replace('class="cx-imgs-h"', 'class="as-h3"'), unsafe_allow_html=True)
    st.markdown('<hr class="rule">', unsafe_allow_html=True)
    heading("Baggage, food &amp; entertainment", level=3)
    amen = f.get("amenities") or {}
    cool = amen.get("cool_thing")
    st.markdown(cabin_facts_html({**f, "amenities": {**amen, "cool_thing": None}}, data=data), unsafe_allow_html=True)
    photo = (config.cabins().get(f"{f.get('airline_iata')}|*") or {}).get("freebie") or {}
    if not (cool or photo.get("image_url")):
        return  # Special freebie only shows when the airline has one (V7 p3)
    st.markdown('<hr class="rule">', unsafe_allow_html=True)
    heading("Special freebie", level=3)
    st.markdown(esc(cool or ""), unsafe_allow_html=True)
    if photo.get("image_url"):
        st.markdown(f'<div class="freebie-img" style="max-width:360px;margin-top:.5rem">'
                    f'{image(photo["image_url"], photo.get("source_page"), cool or "Freebie", 170)}'
                    f'{credit(photo.get("credit"), photo.get("source_page"))}</div>', unsafe_allow_html=True)


def cabin_header(f, qt):
    aircraft = esc(f.get("aircraft_type") or "Aircraft not listed")
    if f.get("aircraft_is_typical"):
        aircraft += ' <span class="typical">Typical aircraft</span>'
    with st.container(key=f"softcard_hdr_{f['fare_id']}"):
        c1, c2, c3 = st.columns([5, 1.4, 1], vertical_alignment="center")
        c1.markdown(f"""<div class="as-h2" style="margin:0">{route_label(f)}</div>
            <div class="as-sub" style="margin:0">{airline_label(f)} · {stops_label(f)} · {aircraft} · {dates_text(f)} ·
            {hm(f.get('depart_time'))} – {hm(f.get('arrive_time'))}</div>""", unsafe_allow_html=True)
        c2.markdown(f'<div style="text-align:right">{price_html(qt, "fc-price")}'
                    + (f'<div class="per-trav">{money(qt.per_traveler)} per traveler</div>' if qt.travelers > 1 else "")
                    + (f'<div class="per-trav">{qt.breakdown()}</div>' if qt.breakdown() else "")
                    + (f'<div class="per-trav">{esc(qt.note)}</div>' if qt.note and _bags_selected() else "")
                    + "</div>", unsafe_allow_html=True)
        with c3:
            st.link_button("Book now", book(f), type="primary", width="stretch",
                           help="Opens Google Flights booking options for this exact flight")


def _bags_selected():
    s = st.session_state.get("search") or {}
    return bool(s.get("carry_on") or s.get("checked"))


def booking_links(f):
    """Optional 'Get booking links' (spends SerpApi calls; falls back to search_url)."""
    from sources import flights_serpapi

    if not flights_serpapi.available() or settings.LIVE_SERPAPI == "off":
        return
    key = f"bk_{f['fare_id']}"
    if st.button("Get booking links", key=key, type="tertiary"):
        try:
            st.session_state[key + "_res"] = flights_serpapi.booking_options(conn(), f)
        except Exception as e:  # quota exhausted or API error -> search_url fallback
            st.session_state[key + "_res"] = []
            st.caption(f"Booking links unavailable ({e}). Use Book now.")
    opts = st.session_state.get(key + "_res")
    if opts:
        st.markdown("".join(f'<div><a class="book-link" href="{esc(o["url"])}" target="_blank">'
                            f'{esc(o.get("book_with") or "Book")} {money(o.get("price"))} →</a></div>'
                            for o in opts if o.get("url")), unsafe_allow_html=True)


# ================================================================ search state
MODES = {"one_way": ("One-way", "One flight, no return"),
         "rt_legs": ("Round trip · separate flights", "Choose your outbound and return one at a time"),
         "rt_bundles": ("Round trip · bundles", "See complete round trips priced together")}
PARTY_ROWS = [("adults", "Adults", "Age 12+"), ("children", "Children", "Age 2–11"),
              ("infants", "Infants", "Under 2")]


def _default_search():
    today = date.today()
    first = config.scan_destinations()[0]["iata"] if config.scan_destinations() else "ATL"
    return {"destination": first, "depart_date": (today + timedelta(days=14)).isoformat(),
            "return_date": (today + timedelta(days=17)).isoformat(), "party": pricing.Party().as_dict(),
            "carry_on": 0, "checked": 0, "mode": "rt_bundles", "nonstop": True}


def search_state():
    """Current search params. Upgrades sessions saved before travelers became a party."""
    ss = st.session_state
    if "search" not in ss:
        ss["search"] = _default_search()
    s = ss["search"]
    if "party" not in s:
        s["party"] = pricing.Party.coerce(s.pop("travelers", 1)).as_dict()
    s.setdefault("mode", "rt_bundles" if s.get("return_date") else "one_way")
    return s


def party_of(s=None):
    return pricing.Party.coerce((s or search_state())["party"])


def _sort_key(name):
    """A–Z that ignores accents, so Cancún sits with the Cs."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()


def dest_rows(query=""):
    """To picker rows, A–Z (V4 p5): (code, city) for each single airport and each multi-airport city.
    The query matches a city name or airport code; an airport also finds its city's group."""
    needle = query.strip().casefold()
    rows, grouped = [], set()

    def hit(*names):
        return not needle or any(needle in n.casefold() for n in names)

    for m in config.METROS:
        airports = config.metro_airports(m)
        if len(airports) > 1:
            grouped.update(airports)
            if hit(config.city(m), *airports, *(config.city(a) for a in airports)):
                rows.append((m, config.city(m)))
    rows += [(d["iata"], d["city"]) for d in config.destinations()
             if d["iata"] not in grouped and hit(d["city"], d["iata"])]
    return sorted(rows, key=lambda r: _sort_key(r[1]))


def airport_short(iata):
    """'ORD · O'Hare' for a checkbox under its city; just the code when the name only repeats it."""
    name = config.city(iata).split("–")[-1]
    return iata if name == iata else f"{iata} · {name}"


def dest_header(code):
    """'New York (All airports)' / 'Atlanta (ATL)' for result headers (V4)."""
    if config.is_metro(code):
        airports = ", ".join(config.metro_airports(code))
        scope = airports if config.is_metro_subset(code) else f"All airports · {airports}"
        return f"{esc(config.city(code))} <span class='muted'>({scope})</span>"
    return f"{esc(config.city(code))} <span class='muted'>({esc(code)})</span>"


def dest_label(iata):
    if config.is_metro_subset(iata):
        return f"{config.city(iata)} · {', '.join(config.metro_airports(iata))}"
    if config.is_metro(iata):
        return f"{config.city(iata)} · all airports"
    d = config.destination(iata) or {}
    label = f"{d.get('city', iata)} ({iata})"
    status = d.get("status")
    if status == "coming_soon":
        label += f" · starts {d.get('status_note') or 'soon'}"
    elif status == "suspending":
        label += " · ending soon"
    elif status == "not_flying":
        label += " · not flying now"
    elif status == "seasonal" or d.get("seasonal"):
        label += " · seasonal"
    return label


def clamp_trip_dates(s, today=None):
    """(depart, return) from saved search params, never before today and return never before depart."""
    today = today or date.today()
    depart = max(date.fromisoformat(s["depart_date"]), today)
    ret = date.fromisoformat(s["return_date"]) if s.get("return_date") else depart + timedelta(days=3)
    if ret < depart:
        ret = depart + timedelta(days=3)
    return depart, ret


# ================================================================ steppers: travelers + bags
def _party_from(prefix):
    ss = st.session_state
    return pricing.Party(ss[f"{prefix}_adults"], ss[f"{prefix}_children"], ss[f"{prefix}_infants"])


def _party_step(prefix, field, delta):
    lo, hi = _party_from(prefix).limits()[field]
    key = f"{prefix}_{field}"
    st.session_state[key] = min(hi, max(lo, st.session_state[key] + delta))
    st.session_state[f"{prefix}_party_pop"] = True  # label changes ("1 adult" -> "2 adults"); keep it open until Done


def _bag_step(prefix, field, delta):
    lo, hi = pricing.bag_limits(_party_from(prefix))[field]
    key = f"{prefix}_{field}"
    st.session_state[key] = min(hi, max(lo, st.session_state[key] + delta))


def _close(key):
    st.session_state[key] = False


def _pm(prefix, field, lo, hi, cb):
    """The '− n +' cluster."""
    val = st.session_state[f"{prefix}_{field}"]
    with st.container(horizontal=True, vertical_alignment="center", gap="small", width="content",
                      key=f"pm_{prefix}_{field}"):
        st.button("−", key=f"{prefix}_{field}_dec", disabled=val <= lo, on_click=cb, args=(prefix, field, -1))
        st.markdown(f'<div class="pm-val">{val}</div>', unsafe_allow_html=True, width="content")
        st.button("+", key=f"{prefix}_{field}_inc", disabled=val >= hi, on_click=cb, args=(prefix, field, 1))


def travelers_control(prefix, initial, label="Travelers *"):
    """'2 adults, 1 child ▾' popover with Adults / Children / Infants steppers and Done (wireframe V2)."""
    ss = st.session_state
    for k, v in pricing.Party.coerce(initial).as_dict().items():
        ss.setdefault(f"{prefix}_{k}", v)
    party = _party_from(prefix)
    limits = party.limits()
    st.markdown(f'<div class="stp-label field">{label}</div>', unsafe_allow_html=True)
    pop_key = f"{prefix}_party_pop"
    with st.popover(party.label(), width="stretch", key=pop_key, on_change="rerun"):
        for field, name, age in PARTY_ROWS:
            with st.container(horizontal=True, vertical_alignment="center", key=f"partyrow_{prefix}_{field}"):
                st.markdown(f'<div class="pr-name"><span class="pr-ico">{ICONS[field]}</span><div><b>{name}</b>'
                            f'<div class="pr-age">{age}</div></div></div>', unsafe_allow_html=True, width="stretch")
                _pm(prefix, field, *limits[field], _party_step)
        if party.infants:
            st.markdown('<div class="credit">Infants must travel with an adult (one lap infant per adult).</div>',
                        unsafe_allow_html=True)
        st.button("Done", key=f"{prefix}_party_done", type="primary", width="stretch", on_click=_close, args=(pop_key,))
    return party


_SVG = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">{}</svg>')
ICONS = {
    "carry_on": _SVG.format('<rect x="6" y="7" width="12" height="14" rx="2"/><path d="M9 7V4h6v3"/><path d="M10 21v1M14 21v1"/>'),
    "checked": _SVG.format('<rect x="4" y="7" width="16" height="13" rx="2"/><path d="M9 7V4h6v3"/><path d="M8 11v5M12 11v5M16 11v5"/>'),
    "adults": _SVG.format('<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>'),
    "children": _SVG.format('<circle cx="12" cy="9" r="3"/><path d="M7 21c0-3 2-5 5-5s5 2 5 5"/>'),
    "infants": _SVG.format('<circle cx="12" cy="10" r="3"/><path d="M9 21c0-2 1-3.5 3-3.5s3 1.5 3 3.5"/><path d="M12 4v1"/>'),
}
BAG_ROWS = {"carry_on": ("Carry-on", ICONS["carry_on"]), "checked": ("Checked", ICONS["checked"])}


def bag_control(prefix, field, initial, party):
    """Cream box: icon · 'Carry-on / Total for trip' · − n +. Bags are trip totals (wireframe V2)."""
    ss = st.session_state
    key = f"{prefix}_{field}"
    lo, hi = pricing.bag_limits(party)[field]
    ss.setdefault(key, initial)
    ss[key] = min(hi, max(lo, ss[key]))  # fewer travelers -> fewer bags allowed
    name, icon = BAG_ROWS[field]
    with st.container(horizontal=True, vertical_alignment="center", key=f"bagbox_{prefix}_{field}"):
        st.markdown(f'<div class="pr-name"><span class="bag-ico">{icon}</span><div><b>{name}</b>'
                    f'<div class="pr-age">Total for trip</div></div></div>', unsafe_allow_html=True, width="stretch")
        _pm(prefix, field, lo, hi, _bag_step)
    return ss[key]


def controls(prefix):
    """(party, carry_on, checked) currently set in a control group (after it has rendered)."""
    ss = st.session_state
    return _party_from(prefix), ss.get(f"{prefix}_carry_on", 0), ss.get(f"{prefix}_checked", 0)


def sync_controls(prefix, s):
    """Copy saved search values into a control group (used when moving between pages)."""
    ss = st.session_state
    for k, v in s["party"].items():
        ss[f"{prefix}_{k}"] = v
    ss[f"{prefix}_carry_on"], ss[f"{prefix}_checked"] = s["carry_on"], s["checked"]


# ================================================================ To picker (V4 p5)
def _dest_close(prefix):
    ss = st.session_state
    ss[f"{prefix}_to_pop"] = False
    ss[f"{prefix}_to_q"] = ""
    ss.pop(f"{prefix}_to_draft", None)


def _dest_tap(prefix, iata):
    st.session_state[f"{prefix}_to"] = iata
    _dest_close(prefix)
    st.session_state["_dest_picked"] = True


def _dest_metro_tick(prefix, metro):
    ss = st.session_state
    ss[f"{prefix}_to_draft"] = list(config.metro_airports(metro)) if ss[f"{prefix}_tick_{metro}"] else []


def _dest_airport_tick(prefix, iata):
    """Ticks stay within one city: ticking an airport in another city starts a new selection."""
    ss = st.session_state
    metro = config.metro_for(iata)
    kept = [a for a in ss[f"{prefix}_to_draft"] if config.metro_for(a) == metro and a != iata]
    ss[f"{prefix}_to_draft"] = kept + [iata] if ss[f"{prefix}_tick_{iata}"] else kept


def _dest_clear(prefix):
    st.session_state[f"{prefix}_to_draft"] = []


def _dest_done(prefix):
    ss = st.session_state
    ss[f"{prefix}_to"] = config.selection_code(ss[f"{prefix}_to_draft"]) or ss[f"{prefix}_to"]
    _dest_close(prefix)
    ss["_dest_picked"] = True


def _dest_list(prefix, draft):
    """Scrolling A–Z list: multi-airport cities get checkboxes, every other city is a single tap."""
    ss = st.session_state
    rows = dest_rows(ss.get(f"{prefix}_to_q", ""))
    if not rows:
        st.markdown('<div class="muted small">No nonstop city matches that.</div>', unsafe_allow_html=True)
    for code, _ in rows:
        if not config.is_metro(code):
            st.button(dest_label(code), key=f"{prefix}_tap_{code}", type="tertiary", width="stretch",
                      on_click=_dest_tap, args=(prefix, code))
            continue
        airports = config.metro_airports(code)
        n = sum(a in draft for a in airports)
        ss[f"{prefix}_tick_{code}"] = n == len(airports)
        with st.container(horizontal=True, vertical_alignment="center", key=f"destmetro_{prefix}_{code}"):
            st.checkbox(f"**{config.city(code)} · all airports**", key=f"{prefix}_tick_{code}", width="stretch",
                        on_change=_dest_metro_tick, args=(prefix, code))
            st.markdown(f'<div class="dest-n">{n} of {len(airports)}</div>', unsafe_allow_html=True, width="content")
        for a in airports:
            ss[f"{prefix}_tick_{a}"] = a in draft
            with st.container(key=f"destairport_{prefix}_{a}"):
                st.checkbox(airport_short(a), key=f"{prefix}_tick_{a}", on_change=_dest_airport_tick, args=(prefix, a))


def dest_picker(prefix, initial):
    """'To (nonstop destinations)': search box, A–Z list, Clear / Done · N airports. Returns the destination code."""
    ss = st.session_state
    to_key, pop_key, draft_key = f"{prefix}_to", f"{prefix}_to_pop", f"{prefix}_to_draft"
    ss.setdefault(to_key, initial)
    st.markdown('<div class="stp-label field">To (nonstop destinations)</div>', unsafe_allow_html=True)
    is_open = ss.get(pop_key, False)
    if not is_open:
        ss.pop(draft_key, None)  # closing without Done drops any ticks
    with st.popover(dest_label(ss[to_key]), width="stretch", key=pop_key, on_change="rerun"):
        if is_open:  # ~110 widgets, so they only exist while the list is showing
            current = ss[to_key]
            ss.setdefault(draft_key, list(config.metro_airports(current)) if config.is_metro(current) or config.metro_for(current) else [])
            _dest_body(prefix)
    return ss[to_key]


@st.fragment
def _dest_body(prefix):
    """Search box + list + Clear / Done. A fragment, so each keystroke pause (live search) reruns only the list.
    Picking a city has to update the button and form outside it, so that triggers a full rerun."""
    ss = st.session_state
    if ss.pop("_dest_picked", False):
        st.rerun()
    draft = ss[f"{prefix}_to_draft"]
    with st.container(key=f"destpick_{prefix}", gap="small"):
        st.markdown('<div class="dest-hint">Every nonstop city from Tampa, A–Z. Tap a city, or tick airports '
                    'for cities with more than one.</div>', unsafe_allow_html=True)
        st.text_input("Search", placeholder="Search city or airport code", key=f"{prefix}_to_q",
                      label_visibility="collapsed", type="search", live="200ms")
        with st.container(height=250, border=False, key=f"destlist_{prefix}"):
            _dest_list(prefix, draft)
        # Pinned to the bottom of the pop-up (theme.py), so Done never needs a scroll to reach.
        with st.container(horizontal=True, gap="small", key=f"destfoot_{prefix}"):
            st.button("Clear", key=f"{prefix}_to_clear", on_click=_dest_clear, args=(prefix,))
            n = len(draft)
            st.button(f"Done · {n} airport{'s' if n != 1 else ''}", key=f"{prefix}_to_done", type="primary",
                      width="stretch", disabled=not n, on_click=_dest_done, args=(prefix,))


# ================================================================ search forms
def _date_inputs(prefix, s, c_dep, c_ret, round_trip):
    ss = st.session_state
    depart, ret_default = clamp_trip_dates(s)
    ss.setdefault(f"{prefix}_dep", depart)
    if ss[f"{prefix}_dep"] < date.today():
        ss[f"{prefix}_dep"] = date.today()
    depart = c_dep.date_input("Depart", min_value=date.today(), format="MM/DD/YYYY", key=f"{prefix}_dep")
    # Return's min is Depart: if Depart moved past Return, shift Return and keep the trip length.
    ss.setdefault(f"{prefix}_ret", ret_default)
    prev = ss.get(f"_{prefix}_prev_dep", depart)
    if ss[f"{prefix}_ret"] < depart:
        stay = (ss[f"{prefix}_ret"] - prev).days
        ss[f"{prefix}_ret"] = depart + timedelta(days=stay if stay > 0 else 3)
    ss[f"_{prefix}_prev_dep"] = depart
    ret = c_ret.date_input("Return", min_value=depart, format="MM/DD/YYYY", disabled=not round_trip, key=f"{prefix}_ret")
    return depart, ret


def _set_mode(key, mode):
    st.session_state[key] = mode


def mode_cards(prefix, current):
    """'How do you want to fly?' — three selectable cards (wireframe V2 p7)."""
    ss = st.session_state
    key = f"{prefix}_mode"
    ss.setdefault(key, current)
    st.markdown('<div class="stp-label" style="margin-bottom:.3rem">How do you want to fly?</div>', unsafe_allow_html=True)
    cols = st.columns(3, gap="small")
    for col, (mode, (title, sub)) in zip(cols, MODES.items()):
        with col:
            active = ss[key] == mode
            with st.container(key=f"modecard{'on' if active else ''}_{prefix}_{mode}"):
                st.button(f"**{title}**  \n{sub}", key=f"{prefix}_pick_{mode}", width="stretch",
                          on_click=_set_mode, args=(key, mode))
    return ss[key]


def trip_form(prefix, title=None, with_modes=False):
    """Home search card (with a Round trip checkbox) or the Ascend Search landing form (with mode cards)."""
    s = search_state()
    ss = st.session_state
    with st.container(key=f"panel_{prefix}"):
        if title:
            heading(title, level=3)
        if with_modes:
            mode = mode_cards(prefix, s["mode"])
            round_trip = mode != "one_way"
        else:
            round_trip = ss.get(f"{prefix}_rt", s["mode"] != "one_way")
        c1, c2, c3, c4, c5 = st.columns([1.05, 1.7, 1, 1, 1.25])
        c1.text_input("From", settings.ORIGIN_LABEL, disabled=True, key=f"{prefix}_from")
        with c2:
            dest = dest_picker(prefix, s["destination"])
        depart, ret = _date_inputs(prefix, s, c3, c4, round_trip)
        with c5:
            party = travelers_control(prefix, s["party"])
        st.markdown('<div class="stp-label" style="margin-top:.3rem">Bags <span class="muted">(optional)</span></div>',
                    unsafe_allow_html=True)
        widths = [2, 2, 0.8, 0.9] if not with_modes else [2, 2, 0.01, 0.9]
        b1, b2, b3, b4 = st.columns(widths, vertical_alignment="center")
        with b1:
            carry = bag_control(prefix, "carry_on", s["carry_on"], party)
        with b2:
            checked = bag_control(prefix, "checked", s["checked"], party)
        if not with_modes:
            b3.checkbox("Round trip", value=round_trip, key=f"{prefix}_rt")
        go = b4.button("Search", type="primary", width="stretch", key=f"{prefix}_go")
        st.markdown('<div class="credit"><span style="color:#B42318">*</span> Required. Infants must travel with an adult. '
                    'Adding bags shows the real total for your trip in the results.</div>', unsafe_allow_html=True)
    if go:
        if not with_modes:
            mode = "one_way" if not round_trip else (s["mode"] if s["mode"] != "one_way" else "rt_bundles")
        ss["search"] = {"destination": dest, "depart_date": depart.isoformat(),
                        "return_date": ret.isoformat() if round_trip else None, "party": party.as_dict(),
                        "carry_on": carry, "checked": checked, "mode": mode, "nonstop": True}
        ss["searched"] = True
        sync_controls("cb", ss["search"])
        if prefix == "land":
            st.rerun()
        st.switch_page(PAGES[config.NAV_SEARCH])


def search_form():
    trip_form("home", "Search nonstop flights from Tampa")


def _summary_line(s):
    """'2 adults, 1 child · 1 carry-on · 1 checked bag · Nonstop only'."""
    bits = [party_of(s).label()]
    if s["carry_on"]:
        bits.append(f"{s['carry_on']} carry-on")
    if s["checked"]:
        bits.append(f"{s['checked']} checked bag{'s' if s['checked'] != 1 else ''}")
    bits.append("Nonstop only" if s.get("nonstop", True) else "Any stops")
    return " · ".join(bits)


def search_bar_compact(s):
    """One-way results bar (wireframe V2 p8). Returns (controls dict, update pressed, change pressed)."""
    with st.container(key="panel_compact"):
        dates = nice_date(s["depart_date"])
        stops = "Nonstop only" if s.get("nonstop", True) else "Any stops"
        top = st.columns([4, 1], vertical_alignment="center")
        top[0].markdown(f"<b>TPA →</b> {dest_header(s['destination'])} · {dates} · One-way · {stops}",
                        unsafe_allow_html=True)
        with top[1], st.container(horizontal=True, horizontal_alignment="right"):
            change = st.button("Change route or dates", type="tertiary", key="change_route")
        c1, c2, c3, c4 = st.columns([1.4, 2, 2, 1], vertical_alignment="bottom")
        with c1:
            party = travelers_control("cb", s["party"])
        with c2:
            st.markdown('<div class="stp-label">Bags <span class="muted">(optional)</span></div>', unsafe_allow_html=True)
            carry = bag_control("cb", "carry_on", s["carry_on"], party)
        with c3:
            st.markdown('<div class="stp-label">&nbsp;</div>', unsafe_allow_html=True)
            checked = bag_control("cb", "checked", s["checked"], party)
        update = c4.button("Update prices", type="primary", width="stretch")
    return {"party": party.as_dict(), "carry_on": carry, "checked": checked}, update, change


def _set_rt(mode):
    s = search_state()
    if mode == "One-way":
        s["mode"] = "one_way"
        s["return_date"] = None
    else:
        if not s.get("return_date"):
            s["return_date"] = (date.fromisoformat(s["depart_date"]) + timedelta(days=3)).isoformat()
        if s["mode"] == "one_way":
            s["mode"] = "rt_bundles"


def inline_choice(label, options, default, key, control=st.segmented_control, width="stretch"):
    """Choice control with its label on the same line, right-aligned ('Show as [Separate legs|Bundles]').
    Pass control=st.pills for the separate rounded Sort buttons (V4 p9, p13)."""
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="right", gap="small",
                      width=width, key=f"inlineseg_{key}"):
        st.markdown(f'<span class="inline-lbl">{label}</span>', unsafe_allow_html=True, width="content")
        val = control(label, options, default=default, key=key, label_visibility="collapsed")
    return val or default


def search_bar_roundtrip(s):
    """Round-trip results bar (V4 p10, p12): summary · One-way|Round trip · Show as Separate legs|Bundles."""
    with st.container(key="panel_rtbar"):
        st.markdown(f"<b>TPA ⇄</b> {dest_header(s['destination'])} · {nice_date(s['depart_date'])} – "
                    f"{nice_date(s['return_date'])}<div class='as-sub' style='margin:0'>{esc(_summary_line(s))}</div>",
                    unsafe_allow_html=True)
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="rtbarrow"):
            trip = st.segmented_control("Trip", ["One-way", "Round trip"], default="Round trip", key="rt_trip",
                                        label_visibility="collapsed")
            show = inline_choice("Show as", ["Separate legs", "Bundles"],
                                 "Bundles" if s["mode"] == "rt_bundles" else "Separate legs", "rt_show", width="content")
            change = st.button("Change route, dates or travelers", type="tertiary", key="change_rt")
    if trip == "One-way":
        _set_rt("One-way")
        st.rerun()
    want = "rt_bundles" if show == "Bundles" else "rt_legs"
    if show and want != s["mode"]:
        s["mode"] = want
        st.rerun()
    return change


# ================================================================ results table
def logo_tile(f):
    code = f.get("airline_iata") or "?"
    url = asset_src(f.get("logo_url") or config.logo_url(code))
    if url:
        return f'<img class="logo-img" src="{esc(url)}" alt="logo">'
    return f'<div class="logo-tile" style="background:{config.brand_color(code)}">{esc(code)}</div>'


def row_cp(f, qt):
    """A CardPrice at exactly the row's quoted price, so Fare & upgrades starts from the price the row shows."""
    party = party_of()
    return pricing.card_price({**f, "price_usd": qt.fare_total, "travelers": qt.travelers}, qt.carry_on, qt.checked,
                              party, include_bags=bool(qt.carry_on or qt.checked))


def row_open(scope, key):
    """Which panel ('fare' / 'cabin') is open under this row, or None."""
    return (st.session_state.get(f"rowopen_{scope}") or {}).get(key)


def row_buttons(scope, key, book_url=None):
    """'Fare & upgrades ▾ · Cabin experience ▾ · Book now' under a result row (V7 p10, p16–17). One panel open at a time."""
    which = row_open(scope, key)

    def flip(panel):
        store = st.session_state.setdefault(f"rowopen_{scope}", {})
        store[key] = None if store.get(key) == panel else panel

    with st.container(horizontal=True, horizontal_alignment="right", gap="small", key=f"rowbtns_{scope}_{key}"):
        st.button(f"Fare & upgrades {'▴' if which == 'fare' else '▾'}", key=f"fx_{scope}_{key}", on_click=flip, args=("fare",))
        st.button(f"Cabin experience {'▴' if which == 'cabin' else '▾'}", key=f"cx_{scope}_{key}", on_click=flip, args=("cabin",))
        if book_url:
            st.link_button("Book now", book_url, type="primary", help="Opens Google Flights booking options for this exact flight")
    return which


def fare_panel(f, cp, key):
    with st.container(key=f"farepanel_{key}", gap="small"):
        st.markdown(bags_line(f, cp, key), unsafe_allow_html=True)
        fare_body(f, cp, key)


def result_row(f, qt, scope="res"):
    cp = row_cp(f, qt)
    key = f"{scope}_{f['fare_id']}"
    added = card_added(f, cp, key)
    open_ = row_open(scope, key)
    with st.container(key=f"resrow{'open' if open_ else ''}_{f['fare_id']}"):
        c0, c1, c2, c3 = st.columns([0.6, 2.8, 2, 1.6], vertical_alignment="center")
        c0.markdown(logo_tile(f), unsafe_allow_html=True)
        c1.markdown(f'<div class="r-main">{route_label(f)}</div><div class="r-sub">{airline_label(f)} · {stops_label(f)}'
                    + (f' · {aircraft_label(f)}' if f.get("aircraft_type") else "")
                    + (f' · {esc(f["flight_numbers"])}' if f.get("flight_numbers") else "") + "</div>",
                    unsafe_allow_html=True)
        c2.markdown(f'<div class="r-main">{hm(f.get("depart_time"))} – {hm(f.get("arrive_time"))}</div>'
                    f'<div class="r-sub">{duration(f.get("duration_min"))}</div>', unsafe_allow_html=True)
        extra = f'<div class="per-trav v3-up">↑ +{money(added)} upgrades</div>' if added else ""
        if qt.travelers > 1:
            extra += f'<div class="per-trav">{money((qt.total + added) / qt.travelers)} per traveler</div>'
        if qt.breakdown():
            extra += f'<div class="per-trav" title="Bag fees vary by route and status">{qt.breakdown()}</div>'
        elif qt.note and _bags_selected():
            extra += f'<div class="per-trav">{esc(qt.note)}</div>'
        est = '<span class="est">est.</span>' if qt.is_estimate else ""
        c3.markdown(f'<span class="r-price">{money(qt.total + added)}{est}</span>' + extra, unsafe_allow_html=True)
        which = row_buttons(scope, key, book(f))
        if which == "fare":
            fare_panel(f, cp, key)
        elif which == "cabin":
            cabin_panel(f)
            booking_links(f)


# ================================================================ round trips (wireframe V2 p9–10)
def true_chips(f, keys=("wifi", "seatback_screen", "power")):
    """Only amenities verified true for this flight."""
    amen = f.get("amenities") or {}
    return "".join(f'<span class="chip">{CHIP_ICONS[k][0]} {CHIP_ICONS[k][1]}</span>' for k in keys if amen.get(k) is True)


def step_heading(n, title, sub, anchor):
    st.markdown(f'<div class="step-h" id="{anchor}"><span class="step-n">{n}</span><div><div class="as-h2" style="margin:0">{title}</div>'
                f'<div class="as-sub" style="margin:0">{sub}</div></div></div>', unsafe_allow_html=True)


def _select(key, fare_id, reset=None):
    ss = st.session_state
    ss[key] = fare_id
    if reset:
        ss.pop(reset, None)
    if key == "sel_out":
        ss["ret_dialog"] = True     # picking an outbound opens the return pop-up
    elif key == "sel_ret":
        ss["ret_picked"] = True     # picking a return closes it


def open_return_dialog():
    st.session_state["ret_dialog"] = True


@st.dialog("Choose your return", width="large")
def return_dialog(rets, selected, sub, totals):
    st.markdown(f'<div class="as-sub">{sub}</div>', unsafe_allow_html=True)
    for r in rets:
        leg_row(r, totals[selected["fare_id"]], r["fare_id"] == selected["fare_id"], "sel_ret", "ret",
                totals[r["fare_id"]])
    if st.session_state.pop("ret_picked", False):
        st.rerun()


def return_slot(out, ret, s):
    """Step 2's dashed box: the route and date, the chosen return once there is one, and the button that opens the pop-up."""
    chosen = (f'<div class="r-sub">{airline_label(ret)} · {hm(ret.get("depart_time"))} – {hm(ret.get("arrive_time"))} · '
              f'{duration(ret.get("duration_min"))}</div>') if ret else ""
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute",
                      key="returnslot"):
        st.markdown(f'<div>{esc(config.city(out["destination"]))} → TPA · {nice_date(s["return_date"])}</div>{chosen}',
                    unsafe_allow_html=True, width="content")
        return st.button("Choose return →", key="choose_return", type="primary", disabled=ret is None,
                         on_click=open_return_dialog)


def hidden_note(n):
    """Says why results are missing when bags are picked."""
    if n:
        what = "1 flight" if n == 1 else f"{n} flights"
        st.markdown(f'<div class="muted small">{what} hidden: bag fees for {"that airline" if n == 1 else "those airlines"} '
                    "aren't verified.</div>", unsafe_allow_html=True)


def cp_at(f, total):
    """A CardPrice whose base fare is `total` (a round-trip total already including any bags), for Fare & upgrades."""
    s = search_state()
    base = pricing.card_price(f, s["carry_on"], s["checked"], party_of(s), include_bags=bool(s["carry_on"] or s["checked"]))
    return replace(base, fare_total=total, with_bags=total if base.with_bags is not None else None)


def leg_row(f, selected_total, is_selected, sel_key, scope, total, reset=None):
    """Radio-style flight row (V7 p16): price is the round-trip total (with any bags); delta vs the selected flight.
    Fare & upgrades and Cabin experience open under the row."""
    key = f"{scope}_{f['fare_id']}"
    cp = cp_at(f, total)
    added = card_added(f, cp, key)
    with st.container(key=f"legrow{'on' if is_selected else ''}_{scope}_{f['fare_id']}"):
        c0, c1, c2, c3, c4, c5 = st.columns([0.28, 0.45, 1.6, 1.45, 1.4, 1.2], vertical_alignment="center")
        c0.button("●" if is_selected else "○", key=f"pick_{scope}_{f['fare_id']}", type="tertiary",
                  on_click=_select, args=(sel_key, f["fare_id"], reset), help="Choose this flight")
        c1.markdown(logo_tile(f), unsafe_allow_html=True)
        c2.markdown(f'<div class="r-main">{airline_label(f)} · {stops_label(f)}</div>'
                    f'<div class="r-sub">{aircraft_label(f) or "Aircraft not listed"}</div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="r-main nowrap">{hm(f.get("depart_time"))} – {hm(f.get("arrive_time"))}</div>'
                    f'<div class="r-sub">{duration(f.get("duration_min"))}</div>', unsafe_allow_html=True)
        none_or_unknown = NO_AMENITIES if has_no_amenities(f.get("amenities")) else "Amenities not verified"
        c4.markdown(true_chips(f) or f'<span class="r-sub">{none_or_unknown}</span>', unsafe_allow_html=True)
        delta = total - selected_total
        est = '<span class="est">est.</span>' if total != f["price_usd"] else ""
        sub = ('<div class="sel-txt">Selected</div>' if is_selected else
               f'<div class="r-sub">{"+" if delta >= 0 else "−"}{money(abs(delta))} vs. selected</div>')
        up = f'<div class="per-trav v3-up">↑ +{money(added)} upgrades</div>' if added else ""
        c5.markdown(f'<div style="text-align:right"><span class="r-price">{money(total + added)}{est}</span>{sub}{up}</div>',
                    unsafe_allow_html=True)
        which = row_buttons(scope, key)
        if which == "fare":
            fare_panel(f, cp, key)
        elif which == "cabin":
            cabin_panel(f)


def _buy(state, text):
    """One 'What this price buys' line: state 'yes' ✓, 'no' ✕, 'unk' – (not verified)."""
    icon = {"yes": "✓", "no": "✕", "unk": "–"}[state]
    return f'<div class="buy2 {state}"><span class="bi">{icon}</span><span>{text}</span></div>'


def price_buys(out, ret, qt, party):
    """'What this price buys' (V4 p10): ✓ included, ✕ costs extra, – not verified. Only verified facts."""
    ao, ar = out.get("amenities") or {}, ret.get("amenities") or {}
    pol = config.policies().get(out.get("airline_iata")) or {}
    lines = []
    wanted = pricing.bags_text(qt.carry_on, qt.checked)
    if not wanted:
        lines.append(_buy("unk", "No bags added — add bags to see the real total"))
    elif qt.bags_total is not None:
        lines.append(_buy("yes", f"{esc(wanted)} bag{'s' if qt.carry_on + qt.checked > 1 else ''} · in the total"))
    else:
        lines.append(_buy("unk", f"{esc(wanted)} · bag fees not verified, not in the total"))
    food = ao.get("food_drinks") if ao.get("food_drinks") == ar.get("food_drinks") else None
    if food:  # same test as change/cancel below: only free food earns the check mark
        lines.append(_buy("yes" if "free" in food.lower() else "no", f"Food & drinks: {esc(food)}"))
    else:
        lines.append(_buy("unk", "Food & drinks: not verified yet"))
    conn_ = [CHIP_ICONS[k][1] for k in ("wifi", "power") if ao.get(k) is True and ar.get(k) is True]
    if conn_:
        lines.append(_buy("yes", f"{' · '.join(conn_)} on both flights"))
    elif all(a.get(k) is False for a in (ao, ar) for k in ("wifi", "power")):
        lines.append(_buy("no", "No Wi-Fi or power on either flight"))
    else:
        lines.append(_buy("unk", "Wi-Fi · power: not verified yet"))
    # Same airline both ways: Google's rules for this exact pair of flights win over the airline-wide ones.
    google = None
    if out.get("airline_iata") == ret.get("airline_iata"):
        google = fare_options.cheapest(fare_options.cached(conn(), out, party, ret)[1])
    seat = (pol.get("seat_selection") or {})
    seat_rule = fare_options.rules(google, "seat selection")
    if seat_rule:
        lines.append(_buy("yes" if seat_rule[0].lower().startswith("free") else "no", esc(seat_rule[0])))
    elif seat.get("fee_usd") == 0:
        lines.append(_buy("yes", "Seat selection included"))
    elif seat.get("fee_usd") is not None:
        lines.append(_buy("no", f"Seat selection · +{money(seat['fee_usd'])} per seat"))
    else:
        lines.append(_buy("unk", "Seat selection: not verified yet"))
    return "".join(lines)


def booking_summary(qt, party, round_trip=True):
    def fee(v):
        return "Included" if v == 0 else (money(v) if v is not None else "Not verified")
    rows = [(f"Fare · {party.label()}", money(qt.fare_total))]
    items = getattr(qt, "items", None) or {}
    if qt.carry_on:
        rows.append((f"Carry-on × {qt.carry_on}", fee(items.get("carry_on"))))
    if qt.checked:
        rows.append((f"Checked bag × {qt.checked}", fee(items.get("checked"))))
    rows.append(("Taxes & fees", "Included in fare"))
    body = "".join(f'<div class="bs-row"><span>{esc(k)}</span><span>{esc(v)}</span></div>' for k, v in rows)
    est = ' <span class="est">est.</span>' if qt.is_estimate else ""
    return (f'{body}<div class="bs-total"><span>Total {"round trip" if round_trip else "trip"}</span>'
            f'<span>{money(qt.total)}{est}</span></div>'
            f'<div class="per-trav" style="text-align:right">{money(qt.per_traveler)} per traveler</div>')


def fare_rows(qt, party):
    """'Fares & prices' (V4 p10). Google prices the party as one total, so a mixed party is split per seat (est.)."""
    def fee(v):
        return "Included" if v == 0 else (money(v) if v is not None else "Not verified")
    seats = max(party.seats, 1)
    each = qt.fare_total / seats
    split = " · split per seat (est.)" if party.children else ""
    rows = [(f"Adult × {party.adults} · {money(each)} each", money(each * party.adults), split)]
    if party.children:
        rows.append((f"Child × {party.children}", money(each * party.children), split))
    if party.infants:
        rows.append((f"Lap infant × {party.infants}", "In fare total", ""))
    rows.append(("Taxes & fees", "Included in fare", ""))
    items = getattr(qt, "items", None) or {}
    bag_bits = [f"carry-on × {qt.carry_on}"] * bool(qt.carry_on) + [f"checked × {qt.checked}"] * bool(qt.checked)
    if bag_bits:
        known = [items.get("carry_on") if qt.carry_on else 0, items.get("checked") if qt.checked else 0]
        total = None if None in known else sum(known)
        rows.append((f"Bags ({', '.join(bag_bits)})", fee(total), ""))
    return "".join(f'<div class="bs-row"><span>{esc(k)}</span><span title="{esc(t.strip(" ·"))}">{esc(v)}</span></div>'
                   for k, v, t in rows)


def leg_card(label, f, anchor=None):
    """Leg in the summary (V5.2 p11): airline · aircraft / times · duration · date / legroom · on time.
    Change scrolls to the outbound list (anchor), or reopens the return pop-up."""
    amen = f.get("amenities") or {}
    facts = []
    if amen.get("legroom_pitch_in"):
        facts.append(f"{esc(str(amen['legroom_pitch_in']))} in legroom")
    ot = q("ontime_pct", f.get("airline_iata"), f.get("destination"))
    if ot is not None:
        facts.append(f"{ot:.0f}% on time")
    when = f"{hm(f.get('depart_time'))} – {hm(f.get('arrive_time'))} · {duration(f.get('duration_min'))} · {nice_date(f.get('depart_date'))}"
    with st.container(key=f"legcard_{label.lower()}", gap=None):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute", gap=None,
                          key=f"lchead_{label.lower()}"):
            st.markdown(f'<span class="leg-lbl">{label}</span>', unsafe_allow_html=True, width="content")
            if anchor:
                st.markdown(f'<a class="book-link" href="#{anchor}" target="_self">Change</a>', unsafe_allow_html=True,
                            width="content")
            else:
                st.button("Change", key="change_return", type="tertiary", on_click=open_return_dialog)
        st.markdown(f'<div class="r-main">{airline_label(f)} · {aircraft_label(f) or "Aircraft not listed"}</div>'
                    f'<div class="r-sub">{when}</div>'
                    f'<div class="r-sub">{" · ".join(facts) if facts else "Legroom and on-time not available yet"}</div>',
                    unsafe_allow_html=True)


def roundtrip_summary(out, ret, s):
    party = party_of(s)
    with st.container(key="softcard_rtsum"):
        st.markdown(f'<div class="fc-top"><span class="as-h2" style="margin:0">Your round trip</span>'
                    f'<span class="muted small">{party.size} traveler{"s" if party.size != 1 else ""}</span></div>',
                    unsafe_allow_html=True)
        leg_card("OUTBOUND", out, "choose-outbound")
        if ret:
            leg_card("RETURN", ret)
        else:
            st.markdown('<div class="leg-card muted">Pick a return flight</div>', unsafe_allow_html=True)
            return
        # Priced only once a return is picked: with no return (none found for this outbound) there's nothing to quote.
        qt = pricing.rt_quote(out, ret, ret["price_usd"], s["carry_on"], s["checked"], party)
        est = ' <span class="est">est.</span>' if qt.is_estimate else ""
        st.markdown(f'<hr class="rule" style="margin:.7rem 0 .5rem"><div class="sum-h">Fares &amp; prices</div>{fare_rows(qt, party)}'
                    f'<div class="sum-h" style="margin-top:.7rem">What this price buys</div>{price_buys(out, ret, qt, party)}'
                    f'<hr class="rule" style="margin:.7rem 0 .5rem"><div class="sum-total"><span>Total round trip</span>'
                    f'<span class="sum-price">{money(qt.total)}{est}</span></div>'
                    f'<div class="per-trav" style="text-align:right">{money(qt.per_traveler)} per traveler</div>',
                    unsafe_allow_html=True)
        st.link_button("Book now", book(out, ret), type="primary", width="stretch",
                       help="Opens Google Flights booking options for this exact round trip")
        st.markdown(f'<div class="credit">You finish booking on {airline_label(out)} or a booking partner. '
                    'Prices are snapshots and may change.</div>', unsafe_allow_html=True)


def _cmp_value(f, key):
    amen = f.get("amenities") or {}
    if key == "aircraft":
        return aircraft_label(f) or "—"
    if key == "ent":
        return amenity_chips(amen) or (NO_AMENITIES if has_no_amenities(amen) else "Not verified")
    if key == "food":
        return esc(amen.get("food_drinks") or "Not verified")
    if key == "bags":
        data = google_fare(f)
        return (f'Carry-on · {_unknown(_carry_text(amen, data))}<br>'
                f'Checked · {_unknown(_checked_text(f, amen, data))}')
    if key == "legroom":
        return _unknown(legroom_text(amen))
    if key == "freebie":
        return esc(amen.get("cool_thing") or "—")
    return "—"


CMP_ROWS = [("aircraft", "Aircraft"), ("bags", "Baggage"), ("food", "Food &amp; drinks"), ("legroom", "Legroom"),
            ("ent", 'Entertainment &amp; power<div class="cmp-sub">hover a chip: outbound / return</div>'),
            ("freebie", 'Special freebie <span class="cmp-sub">(optional)</span>')]


TAG_CLS = {"Best experience": "tag-best", "Lowest price": "tag-low", "Shortest travel time": "tag-short"}
TAG_TEXT = {}


def bundle_table_head():
    """Column labels for the bundles table (V4 p12)."""
    with st.container(key="rthead_bundles"):
        c = st.columns([0.5, 2.6, 2.6, 1.4], vertical_alignment="center")
        for col, label in zip(c, ["Logo", "Route · airline", "Times", "Total price"]):
            col.markdown(f'<div class="rt-head">{label}</div>', unsafe_allow_html=True)


def _times_grid(out, ret):
    def row(lbl, f):
        return (f'<span class="v3-leg">{lbl}</span><span><b>{hm(f.get("depart_time"))} – {hm(f.get("arrive_time"))}</b> '
                f'<span class="muted">{duration(f.get("duration_min"))}</span></span>')
    return f'<div class="v3-legs bt-times">{row("Depart", out)}{row("Return", ret)}</div>'


def bundle_card(b, s, idx):
    """One bundles-table row (V4 p12): logo · tags + route + airline · Depart/Return times · total · actions.
    Fare & upgrades opens the upgrade rows + Booking summary; Cabin experience opens Compare both flights (V7 p17)."""
    from core.experience import EXPLAINER, same_aircraft

    out, ret, sc = b["out"], b["ret"], b["score"]
    party = party_of(s)
    qt = pricing.rt_quote(out, ret, b["fare_total"], s["carry_on"], s["checked"], party)
    key = f"bundle_{idx}"
    open_ = row_open("bundle", key)
    added = card_added({**out, "trip_type": "round_trip"}, cp_at({**out, "trip_type": "round_trip"}, qt.total), key)
    score_tip = (f"Experience score {sc.total:.1f} / 10 · "
                 f"{'same aircraft type both ways' if same_aircraft(out, ret) else 'different aircraft each way'}"
                 f"{'' if sc.complete else ' · limited data'}. {EXPLAINER}")
    tags = "".join(f'<span class="btag {TAG_CLS.get(t, "")}" title="{esc(score_tip)}">{esc(TAG_TEXT.get(t, t))}</span>'
                   for t in b["tags"])
    same_airline = out.get("airline_iata") == ret.get("airline_iata")
    airline = (f"{airline_label(out)} · {stops_label(out)}" + (f" · {aircraft_label(out)}" if out.get("aircraft_type") else "")
               if same_airline else f"Out: {airline_label(out)} · Back: {airline_label(ret)}")
    logos = logo_tile(out) if same_airline else f'<div class="bt-logos">{logo_tile(out)}{logo_tile(ret)}</div>'
    with st.container(key=f"bundlerow{'open' if open_ else ''}_{idx}"):
        c0, c1, c2, c3 = st.columns([0.5, 2.6, 2.6, 1.4], vertical_alignment="center")
        c0.markdown(logos, unsafe_allow_html=True)
        c1.markdown(f'{f"<div class=bt-tags>{tags}</div>" if tags else ""}'
                    f'<div class="r-main">TPA ⇄ {esc(config.city(out["destination"]))}</div>'
                    f'<div class="r-sub">{airline}</div>', unsafe_allow_html=True)
        c2.markdown(_times_grid(out, ret), unsafe_allow_html=True)
        est = '<span class="est">est.</span>' if qt.is_estimate else ""
        each = f'<div class="per-trav">{money(qt.per_traveler)} each</div>' if party.size > 1 else ""
        up = f'<div class="per-trav v3-up">↑ +{money(added)} upgrades</div>' if added else ""
        c3.markdown(f'<div class="bt-price">{money(qt.total + added)}{est}</div><div class="per-trav">round trip</div>{each}{up}',
                    unsafe_allow_html=True)
        which = row_buttons("bundle", key, book(out, ret))
        if which == "cabin":
            with st.container(key=f"bundledetail_{idx}"):
                rows = "".join(f'<tr><td>{label}</td><td>{_cmp_value(out, k)}</td><td>{_cmp_value(ret, k)}</td></tr>'
                               for k, label in CMP_ROWS)
                st.markdown(cabin_images_html(out.get("asset") or {}, 150)
                            + f'<div class="as-h3">Compare both flights</div><table class="cmp"><tr><th></th>'
                            f'<th>OUTBOUND</th><th>RETURN</th></tr>{rows}</table>', unsafe_allow_html=True)
        elif which == "fare":
            cp = cp_at({**out, "trip_type": "round_trip"}, qt.total)
            with st.container(key=f"bundledetail_{idx}"):
                d1, d2 = st.columns([1.2, 1], gap="medium")
                with d1:
                    fare_body({**out, "trip_type": "round_trip"}, cp, key)
                with d2, st.container(key=f"softcard_bs_{idx}"):
                    st.markdown(f'<div class="as-h3" style="margin-top:0">Booking summary</div>{booking_summary(qt, party)}',
                                unsafe_allow_html=True)


# ================================================================ airline matrix
MAX_LISTED = 8  # Matrix cards name up to this many destinations for a Destination type filter


def nonstops_label(a):
    """'[N] nonstops from TPA', or the city itself when there's only one: 'Nonstop to Mexico City'. With a Destination
    type picked, `matching` is the airline's routes of that type, named on the card: Air Canada under International is
    'Nonstop to Halifax · Montreal · Toronto–Pearson' (a count instead when there are more than MAX_LISTED)."""
    routes = a.get("routes") or []
    matching = a.get("matching") or []
    if matching:
        if len(matching) > MAX_LISTED:
            return f"{len(matching)} nonstops to these destinations"
        cities = sorted(config.city(r) for r in matching)
        return "Nonstop to " + " · ".join(cities)  # "·", not ",": some names have a comma (San José, Costa Rica)
    if a["n_nonstops"] == 1 and routes:
        return f"Nonstop to {config.city(routes[0])}"
    return f'{a["n_nonstops"]} nonstop{"s" if a["n_nonstops"] != 1 else ""} from TPA'


def airline_card(a):
    """Matrix tile: one livery photo, centered, with its required credit. The airline page has the four-photo library."""
    asset = a.get("asset") or {}
    with st.container(key=f"card_mx_{a['iata']}"):
        st.markdown(card_photo(asset, 115, "card-img mx-img")
                    + f'<div class="card-body"><div class="mx-name" title="{esc(a["name"])}">{esc(a["name"])}</div>'
                    f'<div class="mx-n">{esc(nonstops_label(a))}</div></div>',
                    unsafe_allow_html=True)
        if st.button("View airline", key=f"view_{a['iata']}", type="primary", width="stretch"):
            st.query_params["airline"] = a["iata"]
            open_at_top()


def open_at_top():
    """Rerun into a new view starting at the top. A rerun keeps the scroll position, so a card low in a grid would
    otherwise open the next view partway down, with its heading off screen."""
    st.session_state["scroll_top"] = True
    st.rerun()


def scroll_to_top_if_asked():
    """Called near the top of a page; scrolls once after open_at_top(), retrying while the new view lays out."""
    if st.session_state.pop("scroll_top", False):
        st.html("<script>(()=>{const go=()=>{const m=document.querySelector('[data-testid=stMain]');"
                "if(m)m.scrollTo(0,0);window.scrollTo(0,0)};go();[50,200,500,1000].forEach(t=>setTimeout(go,t))})()</script>",
                unsafe_allow_javascript=True)


FEE_ROWS = [("personal_item", "Personal item"), ("carry_on", "Carry-on bag"), ("first_checked", "1st checked bag"),
            ("seat_selection", "Seat selection"), ("loyalty_program", "Loyalty program")]


def policy_is_stale(policy, today=None):
    checked = (policy or {}).get("checked")
    if not checked or (policy or {}).get("recheck"):  # recheck: the tracker flags it as due for a re-check
        return True
    return ((today or date.today()) - date.fromisoformat(checked)).days > settings.POLICY_STALE_DAYS


def airline_cabin_card(code, asset):
    """'Cabin experience' on the airline page (V7 p7): Baggage · Food & drinks · Entertainment, typical for the airline."""
    amen = config.amenities().get(f"{code}|*") or {}
    fake = {"airline_iata": code, "amenities": {**amen, "cool_thing": None}}
    with st.container(key=f"softcard_cabin_{code}"):
        st.markdown('<div class="fc-top"><span class="as-h3" style="margin:0">Cabin experience</span>'
                    '<span class="credit">Typical for this airline · economy</span></div>'
                    f'{cabin_facts_html(fake, data={}, cols=3)}', unsafe_allow_html=True)


def airline_freebie(code):
    """'Freebie (if mentioned)' (V7 p7): no box when none is known."""
    cool = (config.amenities().get(f"{code}|*") or {}).get("cool_thing")
    photo = (config.cabins().get(f"{code}|*") or {}).get("freebie") or {}
    if cool or photo.get("image_url"):
        with st.container(key=f"softcard_fact_{code}"):
            pic = (f'<div class="freebie-img">{image(photo["image_url"], photo.get("source_page"), cool or "Freebie", 220, "freebie-pic")}'
                   f'{credit(photo.get("credit"), photo.get("source_page"))}</div>') if photo.get("image_url") else ""
            st.markdown(f'<div class="credit" style="margin:0">Freebie</div><div>{esc(cool or "")}</div>{pic}',
                        unsafe_allow_html=True)


def fees_grid(code, sample=None):
    """`sample` is one of the airline's fares: Google's fares for it show what upgrading costs on a real flight."""
    p = config.policies().get(code) or {}
    name = esc(config.airline_name(code))
    checked = p.get("checked")
    data = google_fare(sample, wait=True) if sample else None
    base = fare_options.cheapest(data)
    with st.container(key=f"softcard_fees_{code}"):
        st.markdown(f"""<div class="fc-top"><span class="as-h3" style="margin:0">Fees &amp; policies at a glance</span>
            <span class="credit">Economy fare · {('checked ' + esc(checked)) if checked else 'not yet checked'}</span></div>""",
                    unsafe_allow_html=True)
        cells = []
        for k, label in FEE_ROWS:
            text = (p.get(k) or {}).get("text")
            v = f'<div class="v">{esc(text)}</div>' if text else '<div class="v unknown">Not verified yet</div>'
            cells.append(f'<div class="fee{" wide" if k == "loyalty_program" else ""}"><div class="k">{label}</div>{v}</div>')
        recent = p.get("recently_changed") or {}
        recent_html = (f'<div class="recent"><b>Recently changed:</b> {esc(recent["text"])}'
                       + (f' · {esc(recent["date"])}' if recent.get("date") else "") + "</div>") if recent.get("text") else \
            '<div class="recent"><b>Recently changed:</b> <span class="muted">nothing logged</span></div>'
        url = p.get("policy_url") or config.airline(code).get("website")
        link = (f'<div style="margin-top:.5rem"><a class="linkish" href="{esc(url)}" target="_blank">'
                f'Full policy on {name} website ↗</a></div>') if url else ""
        warn = ('<div class="credit" style="color:#B42318">Policy not checked in the last '
                f'{settings.POLICY_STALE_DAYS} days — confirm on the airline site.</div>') if policy_is_stale(p) else ""
        ladder = ""
        if base:
            ladder = (f'<details class="fare-more"><summary>Example fares: {route_label(sample)}, '
                      f'{esc(nice_date(sample.get("depart_date")) or "")}</summary>{fare_ladder(data)}'
                      f'<div class="credit">{esc(fare_source_note(data))}</div></details>')
        st.markdown(f'<div class="fees-grid">{"".join(cells)}</div>{ladder}{recent_html}{link}{warn}', unsafe_allow_html=True)


LIBRARY_TILES = (("exterior", "Exterior · livery"), ("interior", "Cabin · economy"), ("seat", "Seat / legroom"),
                 ("food", "Food / perks"))


def library_tiles(asset):
    """The photo library's tiles: all four slots when every one has a photo, otherwise only the ones that do
    (V9: a 3-photo airline gets three stacked photos of the same size, not a grid with an empty box)."""
    have = [(k, label) for k, label in LIBRARY_TILES if asset.get(f"{k}_url")]
    return list(LIBRARY_TILES) if len(have) in (0, 4) else have


def photo_library(asset, code=None):
    tiles = library_tiles(asset)
    if len(tiles) == 4:  # 2 × 2 grid of squares (V8)
        for i in range(0, 4, 2):
            cols = st.columns(2, gap="small")
            for col, (k, label) in zip(cols, tiles[i:i + 2]):
                with col:
                    cls = "lib lib-fit" if k == "exterior" else "lib"
                    st.markdown(image(asset.get(f"{k}_url"), asset.get(f"{k}_link"), label, 190, cls), unsafe_allow_html=True)
    else:  # V9 variation: one column of wide photos, all the same size
        st.markdown("".join(image(asset.get(f"{k}_url"), asset.get(f"{k}_link"), label, 190,
                                  "lib-wide lib-fit" if k == "exterior" else "lib-wide")
                            for k, label in tiles), unsafe_allow_html=True)
    # Wireframes V8: four photos at most, so cabins.json "gallery" extras aren't shown here.
    pairs = [(asset.get(f"{k}_credit"), asset.get(f"{k}_link")) for k, _ in tiles]
    st.markdown(credits_block(pairs) or '<div class="credit">Photos: none yet — add curated images in data/cabins.json</div>',
                unsafe_allow_html=True)


def news_panel(items):
    with st.container(key="softcard_news"):
        heading("Latest news", level=3)
        if not items:
            st.markdown('<div class="muted small">No recent headlines. News refreshes daily.</div>', unsafe_allow_html=True)
            return
        lis = "".join(
            f'<li><a href="{esc(n["url"])}" target="_blank" rel="noopener">{esc(n["headline"])}</a>'
            f'<span class="muted"> · {esc(n.get("source") or "")}{" · " if n.get("source") else ""}'
            f'{esc(nice_date(n.get("published_at")) or "")}</span></li>' for n in items)
        st.markdown(f'<ul class="news">{lis}</ul>', unsafe_allow_html=True)


def reviews_panel(summary, code):
    with st.container(key="softcard_reviews"):
        heading("Passenger reviews", level=3)
        if not summary or not summary.get("review_count"):
            st.markdown('<div class="muted">No reviews yet</div>', unsafe_allow_html=True)
            return
        level = "route-level" if summary["match_level"] == "route" else "airline-wide"
        st.markdown(f"""<div class="as-h2" style="margin:0">★ {summary['stars_5']:.1f} / 5</div>
            <div class="small muted">{summary['review_count']} reviews · {level}
            (General {esc(config.airline_name(code))} economy reviews)</div>
            <div class="small" style="margin-top:.4rem">{esc(summary.get('highlight_pros') or 'Often praised: —')}</div>
            <div class="small">{esc(summary.get('highlight_cons') or 'Common complaints: —')}</div>
            <div class="credit">Source: {esc(settings.REVIEWS_SOURCE)}</div>""", unsafe_allow_html=True)


STATUS_TEXT = {"current": "Year-round", "seasonal": "Seasonal", "coming_soon": "Starting soon", "suspending": "Ending soon",
               "not_flying": "Not flying now"}


def route_status(dest, airline=None):
    """(status, note) for TPA -> dest from destinations.json: that airline's service when given, else the destination's."""
    d = config.destination(dest) or {}
    if airline:
        cs = (d.get("carrier_status") or {}).get(airline) or {}
        return cs.get("status", "current"), cs.get("note")
    return d.get("status") or ("seasonal" if d.get("seasonal") else "current"), d.get("status_note")


def route_availability(dest, airline=None):
    """A sentence for a route that isn't flying year-round, or None: 'Breeze nonstops to Cancun start Dec 19, 2026.'"""
    status, note = route_status(dest, airline)
    who = f"{config.airline_name(airline)} nonstops" if airline else "Nonstops"
    where = f"TPA → {config.city(dest)}"
    if status == "coming_soon":
        return f"{who} on {where} start {note or 'soon'}; there are no flights before then."
    if status == "seasonal":
        when = f" {note}." if note else ""
        return f"{where} is seasonal: {who if airline else 'nonstops'} run only part of the year, so some dates have none.{when}"
    if status == "not_flying":
        return f"{who} on {where} aren't flying right now ({note or 'no flights scheduled'})."
    if status == "suspending":
        return f"{who} on {where} are ending ({note or 'soon'})."
    return None


def unpriced_text(status, last_seen):
    """Why a route row has no price: the route isn't flying yet / this season, or no nonstop turned up lately."""
    if status == "coming_soon":
        return "Not flying yet"
    if status in ("seasonal", "suspending", "not_flying"):
        return "Not flying now"
    at = local_time(last_seen)
    return f"No flights since {at.strftime('%b %-d')}" if at else "No flights found"


def route_search(s, dest, round_trip, fare=None, airline=None, today=None):
    """Search params for a route row: the row's airline, trip type and flight dates, with the saved travelers and bags.
    A row with no price, or whose flight has already left, uses the saved dates instead."""
    today = today or date.today()
    dates = s
    if fare and date.fromisoformat(fare["depart_date"]) >= today:
        dates = {"depart_date": fare["depart_date"], "return_date": fare.get("return_date")}
    depart, ret = clamp_trip_dates(dates, today)
    mode = "one_way" if not round_trip else (s["mode"] if s["mode"] != "one_way" else "rt_bundles")
    return {**s, "destination": dest, "depart_date": depart.isoformat(), "return_date": ret.isoformat() if round_trip else None,
            "mode": mode, "nonstop": True, "airline": airline}


def only_airline(fares, s):
    """Fares for the airline this search was opened from (a route row); all of them for any other search."""
    code = s.get("airline")
    return [f for f in fares if f.get("airline_iata") == code] if code else fares


def airline_notice(s):
    """Say results are limited to one airline, with a way out. True when the user asked to see all airlines."""
    code = s.get("airline")
    if not code:
        return False
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="airlinenotice"):
        st.markdown(f'<div class="small">Showing only <b>{esc(config.airline_name(code))}</b> flights, from Airline Matrix.</div>',
                    unsafe_allow_html=True)
        return st.button("Show all airlines", type="tertiary", key="all_airlines")


def search_route(dest, round_trip, fare=None, airline=None):
    """Open a route row in Ascend Search under exactly the row's conditions (see route_search)."""
    ss = st.session_state
    ss["search"] = route_search(search_state(), dest, round_trip, fare, airline)
    ss["searched"] = True
    sync_controls("cb", ss["search"])
    # The search forms pick the new route up next time they render; the results start from this flight, not an old choice.
    for key in ("home_to", "land_to", "sel_out", "sel_ret", "bundle_mixed", "bundles_shown"):
        ss.pop(key, None)
    st.switch_page(PAGES[config.NAV_SEARCH])


def routes_panel(code, routes):
    """'Routes from TPA' (V9.1 p8): its own One-way / Round-trip toggle; every row opens that flight in Ascend Search
    with the toggle's trip type, so what a row says is what it opens. Weekly frequency isn't in any source, so the
    third column shows the carrier's service status from TPA_Nonstop_Destinations.docx, not a guessed flights/week."""
    ss = st.session_state
    trip = ss.get(f"routes_trip_{code}") or "Round-trip"
    round_trip = trip == "Round-trip"
    priced = q("route_prices", code, "round_trip" if round_trip else "one_way")
    seen = q("last_nonstop_seen", code)
    unit = "round trip" if round_trip else "one-way"
    by_dest = {f["destination"]: f for f in priced}
    dests = {d["iata"]: d for d in config.destinations()}
    rows = sorted(routes, key=lambda r: (r not in by_dest, by_dest[r]["price_usd"] if r in by_dest else 0,
                                         config.city(r)))
    show_all = ss.get(f"routes_all_{code}", False)
    with st.container(key=f"routespanel_{code}"):
        with st.container(horizontal=True, vertical_alignment="center", key=f"rphead_{code}"):
            st.markdown(f'<div class="rp-head"><b>Routes from TPA</b><span>{len(rows)} nonstop route'
                        f'{"s" if len(rows) != 1 else ""} · {esc(config.airline_name(code))} · {unit} fares</span></div>',
                        unsafe_allow_html=True)
            st.segmented_control("Route prices", ["One-way", "Round-trip"], default="Round-trip",
                                 key=f"routes_trip_{code}", label_visibility="collapsed")
        st.markdown('<div class="rp-hint">Select a route to search it in Ascend Search.</div>', unsafe_allow_html=True)
        for r in rows if show_all else rows[:5]:
            f = by_dest.get(r)
            cs = ((dests.get(r) or {}).get("carrier_status") or {}).get(code) or {}
            status = cs.get("note") or STATUS_TEXT.get(cs.get("status"), "")
            if f:
                price = f'from <b>{money(f["price_usd"])}</b> ({unit})'
            else:
                why = route_availability(r, code) or ("No nonstop on the dates we checked in the next few weeks. "
                                                      "Select the route to search other dates.")
                price = (f'<span class="muted" title="{esc(why)}">'
                         f'{unpriced_text(cs.get("status", "current"), seen.get(r))}</span>')
            with st.container(key=f"routerow_{code}_{r}"):
                st.markdown(f'<div class="rp-row"><b>TPA → {esc(config.city(r))}</b>'
                            f'<span class="muted">{aircraft_label(f) if f and f.get("aircraft_type") else "—"}</span>'
                            f'<span class="muted">{esc(status)}</span>'
                            f'<span class="num">{price} <b>›</b></span></div>', unsafe_allow_html=True)
                if st.button(f"Search TPA to {config.city(r)}", key=f"routego_{code}_{r}"):
                    search_route(r, round_trip, f, code)
        if len(rows) > 5:
            label = "Show fewer routes ▴" if show_all else f"Show all routes ({len(rows)}) ▾"
            st.button(label, key=f"routes_btn_{code}", type="tertiary",
                      on_click=lambda: ss.__setitem__(f"routes_all_{code}", not show_all))


def _empty_module(key, label, title, text):
    with st.container(key=f"tileempty_{key}"):
        st.markdown(f'<div class="mod-label">{label}</div><div class="mod-route">{title}</div>'
                    f'<div class="mod-meta">{text}</div>', unsafe_allow_html=True)


DEAL_SLOTS = [("cheapest", "Cheapest flight", "Any number of stops", "No flights found right now"),
              ("fastest_nonstop", "Nonstop flight", "Fastest nonstop on this airline", "No nonstop flight found right now"),
              ("cheapest_nonstop", "Cheapest nonstop flight", "Lowest-priced nonstop", "No nonstop price found right now")]


def _deal_tile(key, tag, note, f, cp, highlight=False):
    """One 'Deals on [airline]' card (V5.1 p7): tag + note, price, route, dates and times, airline, aircraft, bags."""
    with st.container(key=f"{'tilehl' if highlight else 'tile'}_{key}"):
        st.markdown(f'<div class="mod-top"><span class="mod-tag">{tag}</span><span class="mod-note">{note}</span></div>'
                    + headline_html(cp, _unit(f), card_added(f, cp, key))
                    + f'<div class="v3-route"><span class="fc-route">{route_label(f)}</span></div>'
                    + f'<div class="fc-meta">{fare_meta(f)}</div>'
                    + f'<div class="fc-line">{airline_label(f)} · {stops_label(f)}</div>'
                    + f'<div class="fc-line">Aircraft: {aircraft_label(f) or "Not listed"}</div>', unsafe_allow_html=True)
        bags_row(f, cp, key)
        card_actions(f, key, f"airline:{f.get('airline_iata')}", note="Opens Google Flights to confirm the fare.")


def _flight_id(f):
    """Same flights both ways on the same dates. A round trip with another return flight is a different deal."""
    ret = f.get("return_leg") or {}
    return (f.get("flight_numbers"), f.get("depart_date"), f.get("return_date"),
            ret.get("flight_numbers") if isinstance(ret, dict) else None)


def same_flight(deals):
    """The flight to show as one BEST DEAL card, or None to show the three cards.

    Three cards only when they are three different flights. When any two slots hold the same flight (say the
    cheapest flight is also the cheapest nonstop) the page shows that flight once, full width (V9 p16)."""
    fares = [f for f in (deals.get(slot) for slot, *_ in DEAL_SLOTS) if f and f.get("flight_numbers")]
    for i, f in enumerate(fares):
        if any(_flight_id(f) == _flight_id(g) for g in fares[i + 1:]):
            return f
    return None


def _best_deal(code, f, cp):
    """One full-width card tagged BEST DEAL (V6 p17)."""
    key = f"best_{code}"
    with st.container(key=f"tilehl_{key}"):
        left, right = st.columns(2, gap="medium")
        left.markdown('<div class="mod-top"><span class="mod-tag">Best deal</span></div>'
                      + headline_html(cp, _unit(f), card_added(f, cp, key))
                      + f'<div class="v3-route"><span class="fc-route">{route_label(f)}</span></div>'
                      + f'<div class="fc-meta">{fare_meta(f)}</div>'
                      + f'<div class="fc-line">{airline_label(f)} · {stops_label(f)}</div>'
                      + f'<div class="fc-line">Aircraft: {aircraft_label(f) or "Not listed"}</div>', unsafe_allow_html=True)
        with right:
            bags_row(f, cp, key)
            card_actions(f, key, f"airline:{f.get('airline_iata')}", note="Opens Google Flights to confirm the fare.")


def deal_cards(code, deals):
    """Cheapest flight / Nonstop flight / Cheapest nonstop flight. An empty slot keeps its box with a placeholder."""
    s = search_state()
    party = party_of(s)
    carry, checked = s["carry_on"], s["checked"]
    best = same_flight(deals)
    if best:
        cp = card_price(best, party, carry, checked, bool(carry or checked))
        if cp.included or not (carry or checked):
            with cabin_panel_row():
                _best_deal(code, best, cp)
            return
    with cabin_panel_row():
        _deal_row(code, deals, party, carry, checked)


def _deal_row(code, deals, party, carry, checked):
    for col, (slot, tag, note, empty) in zip(st.columns(3, gap="small"), DEAL_SLOTS):
        with col:
            f = deals[slot]
            key = f"{slot}_{code}"
            cp = card_price(f, party, carry, checked, bool(carry or checked)) if f else None
            if f and (cp.included or not (carry or checked)):
                _deal_tile(key, tag, note, f, cp, highlight=slot == "cheapest_nonstop")
            elif f:
                _empty_module(key, tag, "Bag fees aren't verified for this flight",
                              "Remove your bags to see the fare, or check the airline's booking page.")
            else:
                _empty_module(key, tag, empty, "Check back soon or search another date in Ascend Search.")
