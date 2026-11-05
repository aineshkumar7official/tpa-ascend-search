"""Reusable page pieces. Pages only assemble these; all raw HTML lives here (CSS in theme.py)."""
import html
import unicodedata
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from core import booking, config, pricing, queries, theme
from core.config import settings
from core.db import get_conn

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
@st.cache_resource
def conn():
    return get_conn()


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
    return booking.book_url(f, party, return_fare)


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
def chrome(active):
    """Theme + header + nav row + banner. Call first on every page."""
    theme.inject()
    st.markdown(
        f"""<div class="as-header bleed"><div><span class="as-wordmark">{config.PRODUCT_NAME}</span>
        <span class="as-by">{config.BY_LINE}</span></div><div class="as-tagline">{config.TAGLINE}</div></div>""",
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
    """Disclaimer strip on every page; the Explore / About / Data sources columns on Home only (wireframes V4 p1 vs p2-13)."""
    if not full:
        st.markdown(f'<div class="as-footer short bleed"><div class="disc">Credentials / disclaimers: '
                    f'{config.DISCLAIMER_SHORT}</div></div>', unsafe_allow_html=True)
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
  <div class="cols">
    <div><h5>1. Explore</h5>
      {''.join(f'<div><a href="{paths[l]}" target="_self">{l}</a></div>' for l in paths)}
    </div>
    <div><h5>2. About</h5>
      <div>{config.PRODUCT_NAME} finds cheap nonstops out of Tampa (TPA) and shows what the flight is actually like: the plane, the cabin, the bags.</div>
      <div>A project by <b>AK Aviation</b></div>
    </div>
    <div><h5>3. Data sources</h5>
      <div>Fares: Google Flights (via fast-flights){' + SerpApi' if serpapi else ''}</div>
      <div>Photos: Planespotters.net photographers · Wikimedia Commons (credited on each image)</div>
      <div>Reviews: <a href="{settings.REVIEWS_SOURCE_URL}">{esc(settings.REVIEWS_SOURCE)}</a></div>
      <div>Airports: OurAirports (public domain) · News: Google News RSS</div>
      {delay}
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
def image(url, link=None, label="Photo", height=160, cls=""):
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
    """Card image with its required credit laid over the bottom edge, so the card body starts at the price (V4 p1)."""
    return (f'<div class="card-photo">{image(a.get("exterior_url"), a.get("exterior_link"), "Plane photo · airline livery", height, cls)}'
            f'{credit(a.get("exterior_credit"), a.get("exterior_link"))}</div>')


def credits_block(pairs):
    seen, parts = set(), []
    for text, link in pairs:
        if text and text not in seen:
            seen.add(text)
            parts.append(credit(text, link))
    return "".join(parts)


# ================================================================ fare cards (Home + Deals)
def _toggle(scope, fare_id):
    key = f"open_{scope}"
    st.session_state[key] = None if st.session_state.get(key) == fare_id else fare_id



def price_html(qt, size_cls="fc-price"):
    est = '<span class="est">est.</span>' if qt.is_estimate else ""
    return f'<span class="{size_cls}">{money(qt.total)}{est}</span>'


def fare_meta(f):
    return f"{dates_text(f)} · {hm(f.get('depart_time'))} – {hm(f.get('arrive_time'))} · {duration(f.get('duration_min'))}"


def card_actions(f, scope, arrow="↓", cabin=True):
    open_ = st.session_state.get(f"open_{scope}") == f["fare_id"]
    with st.container(horizontal=True, gap="small"):
        st.link_button("Book now", book(f), type="primary", help="Opens Google Flights booking options for this exact flight")
        if cabin:
            st.button(f"Cabin experience {'▴' if open_ else arrow}", key=f"cx_{scope}_{f['fare_id']}",
                      on_click=_toggle, args=(scope, f["fare_id"]))


def bags_chip(qt):
    included = qt.bags_chip().startswith("Price includes")
    return (f'<div class="bag-chip{" on" if included else ""}" title="{esc(qt.breakdown() or qt.note or "")}">'
            f'<span class="bag-chip-ico">{ICONS["checked"]}</span>{esc(qt.bags_chip())}</div>')


# ---------------------------------------------------------------- V3 card pieces
def card_price(f, party, carry, checked, include_bags):
    return pricing.card_price(f, carry, checked, party, include_bags)


def _unit(f):
    return "round trip" if f.get("trip_type") == "round_trip" else "one-way"


def headline_html(cp, after):
    """'[$Price] one-way' / '[$Price] was ~[$Avg]' — price first (V3)."""
    est = '<span class="est">est.</span>' if cp.is_estimate else ""
    return f'<div class="v3-price"><span class="fc-price">{money(cp.headline)}{est}</span><span class="v3-unit">{after}</span></div>'


def legs_html(f):
    """One line for one-way; Depart/Return rows for round trips (V3 p12). Return-leg times aren't
    stored by the scan, so the return row shows its date and leaves times to the booking page."""
    times = f"{hm(f.get('depart_time'))} – {hm(f.get('arrive_time'))} · {duration(f.get('duration_min'))}"
    if f.get("trip_type") != "round_trip" or not f.get("return_date"):
        return f'<div class="fc-meta">{nice_date(f.get("depart_date"))} · {times}</div>'
    return (f'<div class="v3-legs"><span class="v3-leg">Depart</span><span>{nice_date(f.get("depart_date"))} · {times}</span>'
            f'<span class="v3-leg">Return</span><span>{nice_date(f.get("return_date"))} · '
            f'<span class="muted">times on booking page</span></span></div>')


def card_text(f, cp, after, route_tag=""):
    return (headline_html(cp, after)
            + f'<div class="v3-route"><span class="fc-route">{route_label(f)}</span>{route_tag}</div>'
            + legs_html(f)
            + f'<div class="fc-line">{airline_label(f)} · {stops_label(f)}{" · " + aircraft_label(f) if f.get("aircraft_type") else ""}</div>')


def bags_row(f, cp, key):
    """Cream bags box: '[Bags included / not included · $Total with bags]' + Upgrades ▾ menu."""
    with st.container(horizontal=True, key=f"bagrow_{key}", vertical_alignment="center", gap="small"):
        st.markdown(f'<div class="bag-chip v3{" on" if cp.included else ""}" title="{esc(cp.tooltip(money))}">'
                    f'<span class="bag-chip-ico">{ICONS["checked"]}</span><span>{esc(cp.bags_line(money))}</span></div>',
                    unsafe_allow_html=True)
        with st.popover("Upgrades"):
            rows = []
            ups = pricing.upgrades(f, cp.headline, party_of())
            for u in ups:
                if u["fee"] is None and u.get("fee_label"):
                    val = f'<b>{esc(u["fee_label"])}</b>'
                elif u["fee"] is None:
                    val = '<span class="muted"><i>Not verified yet</i></span>'
                else:
                    val = f'+{money(u["fee"])} → <b>{money(u["total"])}</b>'
                rows.append(f'<div class="up-row"><span>{u["label"]}</span><span>{val}</span></div>')
            st.markdown('<div class="up-head">Upgrades for this trip</div>' + "".join(rows)
                        + (f'<div class="credit">Estimated from {airline_label(f)}\'s published economy fees, '
                           'for everyone on the trip. Confirm on the booking page.</div>'
                           if any(u["fee"] is not None for u in ups)
                           else '<div class="credit">See the booking page for prices.</div>'), unsafe_allow_html=True)


def fare_card(f, cp, scope, highlight=False):
    """Home card (V3 p1/p12)."""
    a = f.get("asset") or {}
    key = f"{'cardhl' if highlight else 'card'}_{scope}_{f['fare_id']}"
    with st.container(key=key):
        st.markdown(
            card_photo(a, 135) + f'<div class="card-body">{card_text(f, cp, _unit(f))}</div>',
            unsafe_allow_html=True)
        bags_row(f, cp, f"{scope}_{f['fare_id']}")
        card_actions(f, scope)


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


def trend_chart(days, avg=None, w=300, h=90):
    """Daily-price line chart. Hover/tap any day for '[Date] · [$Price]' and the change vs. the day before
    (pure HTML/CSS so it works inside a card without a rerun)."""
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
    return (f'<div class="tc">{label(last)}'
            f'<div class="tc-plot">{svg}<div class="tc-dot tc-last" style="left:{x(last) / w * 100:.2f}%;'
            f'top:{y(vals[last]) / h * 100:.2f}%"></div><div class="tc-hits">{hits}</div></div>'
            f'<div class="tc-axis"><span>{_day(days[0][0])}</span><span>Low {money(lo)} · High {money(hi)}</span>'
            f'<span>{_day(days[-1][0])}</span></div></div>')


def _drop_text(d, label):
    if d["tracking"]:
        return '<span class="tr-pct flat">Tracking — trend available soon</span>'
    pct = round((d["drop_pct"] or 0) * 100)
    cls = "down" if pct > 0 else ("up" if pct < 0 else "flat")
    arrow = "▼" if pct > 0 else ("▲" if pct < 0 else "–")
    return f'<span class="tr-pct {cls}">{arrow} {abs(pct)}% {label}</span>'


def trend_row(d, uid, scale=1.0, ranges=None, label="over 14 days", hint="Tap or hover for daily prices"):
    """Collapsible trend row (V3): mini sparkline + '▼ X% over 14 days', opening to the daily chart.
    `ranges` (e.g. (7, 14, 30)) adds day-range tabs (Airline page)."""
    days_all = daily_points(d.get("points") or [], scale)
    if not days_all:
        return ('<div class="tr-box"><div class="tr-sum static"><span class="tr-txt">'
                f'{_drop_text(d, label)}<span class="tr-hint">Price checks start with the next scan</span></span></div></div>')
    avg = d["baseline"] * scale if d.get("baseline") else None
    cutoff = days_all[-1][0]

    def window(n):
        return [(dt, p) for dt, p in days_all if (cutoff - dt).days < n]

    if ranges:
        default = 14 if 14 in ranges else ranges[0]
        tabs = "".join(f'<input type="radio" class="tr-r tr-r{n}" name="tr_{uid}" id="tr_{uid}_{n}"'
                       f'{" checked" if n == default else ""}>' for n in ranges)
        lbls = "".join(f'<label class="l{n}" for="tr_{uid}_{n}">{n} days</label>' for n in ranges)
        panes = "".join(f'<div class="tr-pane p{n}">{trend_chart(window(n), avg)}</div>' for n in ranges)
        body = f'{tabs}<div class="tr-tabs">{lbls}</div>{panes}'
        mini = [p for _, p in window(default)]
    else:
        days = window(14)
        body = trend_chart(days, avg)
        mini = [p for _, p in days]
    hint_txt = hint if len(days_all) >= 2 else f"{len(days_all)} day of price checks so far"
    return (f'<details class="tr-box"><summary class="tr-sum">{_spark_mini(mini)}<span class="tr-txt">'
            f'{_drop_text(d, label)}<span class="tr-hint">{hint_txt}</span></span><span class="tr-caret">▾</span></summary>'
            f'<div class="tr-body">{body}<div class="credit">Lowest nonstop price seen each day for this date window'
            f'{", for your travelers" if scale != 1 else ""}.</div></div></details>')


def deal_card(d, cp, scope):
    """Ascend Deals card (V3 p2): '$Price was ~$Avg', bags + Upgrades, collapsible daily-price trend."""
    f, a = d["fare"], d["fare"].get("asset") or {}
    after = _unit(f)  # until the route has a baseline, just say one-way / round trip
    if not d["tracking"] and d.get("baseline"):
        # Same basis as the headline: fare-only baseline, plus the same bag estimate when bags are included.
        was = d["baseline"] * cp.travelers + (cp.headline - cp.fare_total)
        after = f"was ~{money(was)}"
    with st.container(key=f"card_{scope}_{f['fare_id']}"):
        st.markdown(
            card_photo(a, 125) + f'<div class="card-body">{card_text(f, cp, after)}</div>',
            unsafe_allow_html=True)
        bags_row(f, cp, f"{scope}_{f['fare_id']}")
        st.markdown(f'<div class="tr-wrap">{trend_row(d, f"{scope}{f["fare_id"]}", scale=cp.travelers)}</div>',
                    unsafe_allow_html=True)
        card_actions(f, scope, "▾")



def card_grid(items, render, cols=3):
    for i in range(0, len(items), cols):
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


def amenity_chips(amen):
    """Chips only for amenities that are true. Missing/false keys render nothing."""
    return "".join(f'<span class="chip">{icon} {label}</span>'
                   for k, (icon, label) in CHIP_ICONS.items() if (amen or {}).get(k) is True)


NO_AMENITIES = "No Wi-Fi, screens or power"


def has_no_amenities(amen):
    """True only when all four are verified false; missing/null stays 'not verified'."""
    return all((amen or {}).get(k) is False for k in CHIP_ICONS)


def entertainment_html(amen):
    """Chips for what's on board, a plain 'none' when verified absent, otherwise 'not verified'."""
    return amenity_chips(amen) or _amen_value(NO_AMENITIES if has_no_amenities(amen) else None)


def _amen_value(v, unknown="Not verified yet"):
    return f'<div class="v">{esc(str(v))}</div>' if v else f'<div class="v unknown">{unknown}</div>'


def cabin_images(a, labels=("Cabin photo", "Seat photo", "Perk photo"), height=110):
    slots = [("interior_url", "interior_link", "interior_credit"), ("seat_url", "seat_link", "seat_credit"),
             ("food_url", "food_link", "food_credit")]
    cols = st.columns(3, gap="small")
    for col, (u, l, _), label in zip(cols, slots, labels):
        with col:
            st.markdown(image(a.get(u), a.get(l), label, height), unsafe_allow_html=True)
    st.markdown(credits_block([(a.get(c), a.get(l)) for _, l, c in slots]), unsafe_allow_html=True)


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


def cabin_panel(f, compact=True):
    """Inline cabin panel (result rows, Home/Deals cards). compact=False is the standalone view body."""
    a, amen = f.get("asset") or {}, f.get("amenities") or {}
    if compact:
        with st.container(key=f"cabinpanel_{f['fare_id']}"):
            cabin_images(a)
            c1, c2, c3 = st.columns(3, gap="small")
            c1.markdown(f'<div class="amen"><div class="k">Carry-on</div>{_amen_value(amen.get("carry_on"))}</div>',
                        unsafe_allow_html=True)
            c2.markdown(f'<div class="amen"><div class="k">Food &amp; drinks</div>{_amen_value(amen.get("food_drinks"))}</div>',
                        unsafe_allow_html=True)
            c3.markdown(f'<div class="amen"><div class="k">Entertainment</div>{entertainment_html(amen)}</div>',
                        unsafe_allow_html=True)
            cool = amen.get("cool_thing")
            st.markdown(f'<div style="margin-top:.6rem"><b>Special freebies:</b> '
                        f'{esc(cool) if cool else "<span class=muted>Coming soon</span>"} {typical_tag(f)}</div>',
                        unsafe_allow_html=True)
            page = PAGES.get(config.NAV_SEARCH)
            if page is not None:
                st.page_link(page, label="Open full cabin experience ↗", query_params={"fare_id": f["fare_id"]})
        return
    heading("Cabin experience", level=2)
    heading("Cabin images", level=3)
    cols = st.columns(3, gap="small")
    for col, (u, l, label) in zip(cols, [("exterior_url", "exterior_link", "The plane"),
                                         ("interior_url", "interior_link", "Seats"),
                                         ("food_url", "food_link", "Food/drink")]):
        with col:
            st.markdown(image(a.get(u), a.get(l), label, 150), unsafe_allow_html=True)
    st.markdown(credits_block([(a.get("exterior_credit"), a.get("exterior_link")),
                               (a.get("interior_credit"), a.get("interior_link")),
                               (a.get("food_credit"), a.get("food_link"))]), unsafe_allow_html=True)
    st.markdown('<hr class="rule">', unsafe_allow_html=True)
    heading(f"Amenities: specifics {typical_tag(f)}", level=3)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.markdown(f'<div class="amen"><div class="k">Carry-on</div>{_amen_value(amen.get("carry_on"))}</div>',
                unsafe_allow_html=True)
    c2.markdown(f'<div class="amen"><div class="k">Food &amp; drinks</div>{_amen_value(amen.get("food_drinks"))}</div>',
                unsafe_allow_html=True)
    c3.markdown(f'<div class="amen"><div class="k">Entertainment</div>{entertainment_html(amen)}'
                f'<div class="credit">Shows only what this flight offers</div></div>', unsafe_allow_html=True)
    pitch = amen.get("legroom_pitch_in")
    c4.markdown(f'<div class="amen"><div class="k">Legroom</div>{_amen_value(f"{pitch} in pitch" if pitch else None)}</div>',
                unsafe_allow_html=True)
    st.markdown('<hr class="rule">', unsafe_allow_html=True)
    heading("Special freebies", level=3)
    cool = amen.get("cool_thing")
    st.markdown(esc(cool) if cool else '<span class="muted">Coming soon</span>', unsafe_allow_html=True)


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

    if not flights_serpapi.available():
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
            draft = ss.setdefault(draft_key, list(config.metro_airports(current)) if config.is_metro(current) or config.metro_for(current) else [])
            with st.container(key=f"destpick_{prefix}"):
                st.markdown('<div class="dest-hint">Every nonstop city from Tampa, A–Z. Cities with more than one airport '
                            'have checkboxes: tick them all or only the ones you want. Other cities are a single tap.</div>',
                            unsafe_allow_html=True)
                st.text_input("Search", placeholder="Search city or airport code", key=f"{prefix}_to_q",
                              label_visibility="collapsed")
                with st.container(height=340, border=False, key=f"destlist_{prefix}"):
                    _dest_list(prefix, draft)
                clear, done = st.columns([1, 3.2], gap="small")
                clear.button("Clear", key=f"{prefix}_to_clear", width="stretch", on_click=_dest_clear, args=(prefix,))
                n = len(draft)
                done.button(f"Done · {n} airport{'s' if n != 1 else ''}", key=f"{prefix}_to_done", type="primary",
                            width="stretch", disabled=not n, on_click=_dest_done, args=(prefix,))
    return ss[to_key]


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
    if f.get("logo_url"):
        return f'<img class="logo-img" src="{esc(f["logo_url"])}" alt="logo">'
    code = f.get("airline_iata") or "?"
    return f'<div class="logo-tile" style="background:{config.brand_color(code)}">{esc(code)}</div>'


def result_row(f, qt, scope="res"):
    open_ = st.session_state.get(f"open_{scope}") == f["fare_id"]
    with st.container(key=f"resrow{'open' if open_ else ''}_{f['fare_id']}"):
        c0, c1, c2, c3, c4 = st.columns([0.6, 2.4, 2, 1.4, 1.6], vertical_alignment="center")
        c0.markdown(logo_tile(f), unsafe_allow_html=True)
        c1.markdown(f'<div class="r-main">{route_label(f)}</div><div class="r-sub">{airline_label(f)} · {stops_label(f)}'
                    + (f' · {aircraft_label(f)}' if f.get("aircraft_type") else "")
                    + (f' · {esc(f["flight_numbers"])}' if f.get("flight_numbers") else "") + "</div>",
                    unsafe_allow_html=True)
        c2.markdown(f'<div class="r-main">{hm(f.get("depart_time"))} – {hm(f.get("arrive_time"))}</div>'
                    f'<div class="r-sub">{duration(f.get("duration_min"))}</div>', unsafe_allow_html=True)
        extra = ""
        if qt.travelers > 1:
            extra += f'<div class="per-trav">{money(qt.per_traveler)} per traveler</div>'
        if qt.breakdown():
            extra += f'<div class="per-trav" title="Bag fees vary by route and status">{qt.breakdown()}</div>'
        elif qt.note and _bags_selected():
            extra += f'<div class="per-trav">{esc(qt.note)}</div>'
        c3.markdown(price_html(qt, "r-price") + extra, unsafe_allow_html=True)
        with c4:
            st.button(f"Cabin experience {'▴' if open_ else '▾'}", key=f"cx_{scope}_{f['fare_id']}",
                      on_click=_toggle, args=(scope, f["fare_id"]), width="stretch")
            st.link_button("Book now", book(f), type="primary", width="stretch",
                           help="Opens Google Flights booking options for this exact flight")
    if open_:
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
def return_dialog(rets, selected, sub):
    st.markdown(f'<div class="as-sub">{sub}</div>', unsafe_allow_html=True)
    for r in rets:
        leg_row(r, selected["price_usd"], r["fare_id"] == selected["fare_id"], "sel_ret", "ret")
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


def leg_row(f, selected_price, is_selected, sel_key, scope, reset=None):
    """Radio-style flight row: price is the round-trip total; delta vs the selected flight."""
    with st.container(key=f"legrow{'on' if is_selected else ''}_{scope}_{f['fare_id']}"):
        c0, c1, c2, c3, c4, c5, c6 = st.columns([0.28, 0.45, 1.45, 1.45, 0.85, 1.0, 1.8], vertical_alignment="center")
        c0.button("●" if is_selected else "○", key=f"pick_{scope}_{f['fare_id']}", type="tertiary",
                  on_click=_select, args=(sel_key, f["fare_id"], reset), help="Choose this flight")
        c1.markdown(logo_tile(f), unsafe_allow_html=True)
        c2.markdown(f'<div class="r-main">{airline_label(f)} · {stops_label(f)}</div>'
                    f'<div class="r-sub">{aircraft_label(f) or "Aircraft not listed"}</div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="r-main nowrap">{hm(f.get("depart_time"))} – {hm(f.get("arrive_time"))}</div>'
                    f'<div class="r-sub">{duration(f.get("duration_min"))}</div>', unsafe_allow_html=True)
        none_or_unknown = NO_AMENITIES if has_no_amenities(f.get("amenities")) else "Amenities not verified"
        c4.markdown(true_chips(f) or f'<span class="r-sub">{none_or_unknown}</span>', unsafe_allow_html=True)
        delta = f["price_usd"] - (selected_price or f["price_usd"])
        sub = ('<div class="sel-txt">Selected</div>' if is_selected else
               f'<div class="r-sub">{"+" if delta >= 0 else "−"}{money(abs(delta))} vs. selected</div>')
        c5.markdown(f'<div style="text-align:right"><span class="r-price">{money(f["price_usd"])}</span>{sub}</div>',
                    unsafe_allow_html=True)
        open_ = st.session_state.get(f"open_{scope}") == f["fare_id"]
        c6.button(f"Cabin experience {'▴' if open_ else '▾'}", key=f"cx_{scope}_{f['fare_id']}",
                  on_click=_toggle, args=(scope, f["fare_id"]), width="stretch")
    if st.session_state.get(f"open_{scope}") == f["fare_id"]:
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
    seat = (pol.get("seat_selection") or {})
    if seat.get("fee_usd") == 0:
        lines.append(_buy("yes", "Seat selection included"))
    elif seat.get("fee_usd") is not None:
        lines.append(_buy("no", f"Seat selection · +{money(seat['fee_usd'])} per seat"))
    else:
        lines.append(_buy("unk", "Seat selection: not verified yet"))
    chg = (pol.get("change_cancel") or {}).get("text")
    if chg:
        lines.append(_buy("yes" if "free" in chg.lower() else "no", f"Change or cancel · {esc(chg)}"))
    else:
        lines.append(_buy("unk", "Change or cancel: not verified yet"))
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
    qt = pricing.rt_quote(out, ret, ret["price_usd"] if ret else out["price_usd"], s["carry_on"], s["checked"], party)
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
    if key == "legroom":
        return f'{amen["legroom_pitch_in"]} in pitch' if amen.get("legroom_pitch_in") else "Not verified"
    if key == "ent":
        return (true_chips(f, ("wifi", "seatback_screen", "stream_to_device", "power"))
                or (NO_AMENITIES if has_no_amenities(amen) else "Not verified"))
    if key == "food":
        return esc(amen.get("food_drinks") or "Not verified")
    if key == "bags":
        return esc(amen.get("carry_on") or "Not verified")
    return "—"


CMP_ROWS = [("aircraft", "Aircraft"), ("legroom", "Legroom"), ("ent", "Wi-Fi & entertainment"),
            ("food", "Food & drinks"), ("bags", "Carry-on / checked")]


TAG_CLS = {"Best experience": "tag-best", "Lowest price": "tag-low", "Shortest travel time": "tag-short"}
TAG_TEXT = {}


def bundle_table_head():
    """Column labels for the bundles table (V4 p12)."""
    with st.container(key="rthead_bundles"):
        c = st.columns([0.5, 2.3, 2.45, 1.1, 1.85], vertical_alignment="center")
        for col, label in zip(c, ["Logo", "Route · airline", "Times", "Total price", ""]):
            col.markdown(f'<div class="rt-head">{label}</div>', unsafe_allow_html=True)


def _times_grid(out, ret):
    def row(lbl, f):
        return (f'<span class="v3-leg">{lbl}</span><span><b>{hm(f.get("depart_time"))} – {hm(f.get("arrive_time"))}</b> '
                f'<span class="muted">{duration(f.get("duration_min"))}</span></span>')
    return f'<div class="v3-legs bt-times">{row("Depart", out)}{row("Return", ret)}</div>'


def bundle_card(b, s, idx):
    """One bundles-table row (V4 p12): logo · tags + route + airline · Depart/Return times · total · actions.
    'Cabin experience' opens Compare both flights + Booking summary."""
    from core.experience import EXPLAINER, same_aircraft

    out, ret, sc = b["out"], b["ret"], b["score"]
    party = party_of(s)
    qt = pricing.rt_quote(out, ret, b["total"], s["carry_on"], s["checked"], party)
    key = f"bundle_{idx}"
    open_ = st.session_state.get("open_bundle") == key
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
        c0, c1, c2, c3, c4 = st.columns([0.5, 2.3, 2.45, 1.1, 1.85], vertical_alignment="center")
        c0.markdown(logos, unsafe_allow_html=True)
        c1.markdown(f'{f"<div class=bt-tags>{tags}</div>" if tags else ""}'
                    f'<div class="r-main">TPA ⇄ {esc(config.city(out["destination"]))}</div>'
                    f'<div class="r-sub">{airline}</div>', unsafe_allow_html=True)
        c2.markdown(_times_grid(out, ret), unsafe_allow_html=True)
        est = '<span class="est">est.</span>' if qt.is_estimate else ""
        each = f'<div class="per-trav">{money(qt.per_traveler)} each</div>' if party.size > 1 else ""
        c3.markdown(f'<div class="bt-price">{money(qt.total)}{est}</div><div class="per-trav">round trip</div>{each}',
                    unsafe_allow_html=True)
        with c4:
            st.button(f"Cabin experience {'▴' if open_ else '▾'}", key=f"ts_{idx}", width="stretch",
                      on_click=_toggle, args=("bundle", key))
            st.link_button("Book now", book(out, ret), type="primary", width="stretch",
                           help="Opens Google Flights booking options for this exact round trip")
        if open_:
            with st.container(key=f"bundledetail_{idx}"):
                d1, d2 = st.columns([1.5, 1], gap="medium")
                rows = "".join(f'<tr><td>{label}</td><td>{_cmp_value(out, k)}</td><td>{_cmp_value(ret, k)}</td></tr>'
                               for k, label in CMP_ROWS)
                d1.markdown(f'<div class="as-h3" style="margin-top:0">Compare both flights</div><table class="cmp"><tr><th></th>'
                            f'<th>OUTBOUND</th><th>RETURN</th></tr>{rows}</table>', unsafe_allow_html=True)
                with d2:
                    with st.container(key=f"softcard_bs_{idx}"):
                        st.markdown(f'<div class="as-h3" style="margin-top:0">Booking summary</div>{booking_summary(qt, party)}',
                                    unsafe_allow_html=True)
                        st.link_button("Book now", book(out, ret), type="primary", width="stretch", key=f"bk2_{idx}")


# ================================================================ airline matrix
def airline_card(a):
    """Matrix tile: API livery photo (Planespotters, else Wikimedia Commons) with its required credit."""
    asset = a.get("asset") or {}
    with st.container(key=f"card_mx_{a['iata']}"):
        st.markdown(card_photo(asset, 115, "card-img mx-img")
                    + f'<div class="card-body"><div class="mx-name" title="{esc(a["name"])}">{esc(a["name"])}</div>'
                    f'<div class="mx-n">{a["n_nonstops"]} nonstop{"s" if a["n_nonstops"] != 1 else ""} from TPA</div></div>',
                    unsafe_allow_html=True)
        if st.button("View airline", key=f"view_{a['iata']}", type="primary", width="stretch"):
            st.query_params["airline"] = a["iata"]
            st.rerun()


FEE_ROWS = [("personal_item", "Personal item"), ("carry_on", "Carry-on bag"), ("first_checked", "1st checked bag"),
            ("seat_selection", "Seat selection"), ("change_cancel", "Change / cancel"), ("loyalty_program", "Loyalty program")]


def policy_is_stale(policy, today=None):
    checked = (policy or {}).get("checked")
    if not checked:
        return True
    return ((today or date.today()) - date.fromisoformat(checked)).days > settings.POLICY_STALE_DAYS


def fee_table_cell(item):
    """Full-width Change / cancel cell from rows/note; None when the policy only has plain text."""
    rows = (item or {}).get("rows")
    if not rows:
        return None
    label = f' · {esc(item["label"])}' if item.get("label") else ""
    body = "".join(f'<div class="fee-row"><span>{esc(what)}</span><b>{esc(fee)}</b></div>' for what, fee in rows)
    note = f'<div class="fee-note">{esc(item["note"])}</div>' if item.get("note") else ""
    return f'<div class="fee wide"><div class="k">Change / cancel{label}</div>{body}{note}</div>'


def fees_grid(code):
    p = config.policies().get(code) or {}
    name = esc(config.airline_name(code))
    checked = p.get("checked")
    with st.container(key=f"softcard_fees_{code}"):
        st.markdown(f"""<div class="fc-top"><span class="as-h3" style="margin:0">Fees &amp; policies at a glance</span>
            <span class="credit">Economy fare · {('checked ' + esc(checked)) if checked else 'not yet checked'}</span></div>""",
                    unsafe_allow_html=True)
        cells = []
        for k, label in FEE_ROWS:
            table = fee_table_cell(p.get(k))
            if table:
                cells.append(table)
                continue
            text = (p.get(k) or {}).get("text")
            v = f'<div class="v">{esc(text)}</div>' if text else '<div class="v unknown">Not verified yet</div>'
            cells.append(f'<div class="fee"><div class="k">{label}</div>{v}</div>')
        recent = p.get("recently_changed") or {}
        recent_html = (f'<div class="recent"><b>Recently changed:</b> {esc(recent["text"])}'
                       + (f' · {esc(recent["date"])}' if recent.get("date") else "") + "</div>") if recent.get("text") else \
            '<div class="recent"><b>Recently changed:</b> <span class="muted">nothing logged</span></div>'
        url = p.get("policy_url") or config.airline(code).get("website")
        link = (f'<div style="margin-top:.5rem"><a class="linkish" href="{esc(url)}" target="_blank">'
                f'Full policy on {name} website ↗</a></div>') if url else ""
        warn = ('<div class="credit" style="color:#B42318">Policy not checked in the last '
                f'{settings.POLICY_STALE_DAYS} days — confirm on the airline site.</div>') if policy_is_stale(p) else ""
        st.markdown(f'<div class="fees-grid">{"".join(cells)}</div>{recent_html}{link}{warn}', unsafe_allow_html=True)


def photo_library(asset):
    tiles = [("exterior", "Exterior · livery"), ("interior", "Cabin · economy"), ("seat", "Seat / legroom"),
             ("food", "Food / perks")]
    for i in range(0, 4, 2):
        cols = st.columns(2, gap="small")
        for col, (k, label) in zip(cols, tiles[i:i + 2]):
            with col:
                st.markdown(image(asset.get(f"{k}_url"), asset.get(f"{k}_link"), label, 105), unsafe_allow_html=True)
    st.markdown(credits_block([(asset.get(f"{k}_credit"), asset.get(f"{k}_link")) for k, _ in tiles])
                or '<div class="credit">Photos: none yet — add curated images in data/cabins.json</div>',
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


STATUS_TEXT = {"current": "Year-round", "seasonal": "Seasonal", "coming_soon": "Starting soon", "suspending": "Ending soon"}


def search_route(dest, round_trip):
    """Run this route in Ascend Search with the saved dates, travelers and bags (V5.1 p7)."""
    ss = st.session_state
    s = search_state()
    depart, ret = clamp_trip_dates(s)
    mode = "one_way" if not round_trip else (s["mode"] if s["mode"] != "one_way" else "rt_bundles")
    ss["search"] = {**s, "destination": dest, "depart_date": depart.isoformat(),
                    "return_date": ret.isoformat() if round_trip else None, "mode": mode, "nonstop": True}
    ss["searched"] = True
    sync_controls("cb", ss["search"])
    for key in ("home_to", "land_to"):  # the search forms pick the new route up next time they render
        ss.pop(key, None)
    st.switch_page(PAGES[config.NAV_SEARCH])


def routes_panel(code, routes, priced):
    """'Routes from TPA' (V5.1 p7): every row searches that route. Weekly frequency isn't in any source, so the
    third column shows the carrier's service status from TPA_Nonstop_Destinations.docx, not a guessed flights/week."""
    by_dest = {f["destination"]: f for f in priced}
    dests = {d["iata"]: d for d in config.destinations()}
    rows = sorted(routes, key=lambda r: (r not in by_dest, by_dest[r]["price_usd"] if r in by_dest else 0,
                                         config.city(r)))
    ss = st.session_state
    show_all = ss.get(f"routes_all_{code}", False)
    with st.container(key=f"routespanel_{code}"):
        st.markdown(f'<div class="rp-head"><b>Routes from TPA</b><span>{len(rows)} nonstop route'
                    f'{"s" if len(rows) != 1 else ""} · {esc(config.airline_name(code))}</span></div>'
                    '<div class="rp-hint">Select a route to search it in Ascend Search.</div>', unsafe_allow_html=True)
        for r in rows if show_all else rows[:5]:
            f = by_dest.get(r)
            cs = ((dests.get(r) or {}).get("carrier_status") or {}).get(code) or {}
            status = cs.get("note") or STATUS_TEXT.get(cs.get("status"), "")
            price = f'from <b>{money(f["price_usd"])}</b>' if f else '<span class="muted">not priced</span>'
            with st.container(key=f"routerow_{code}_{r}"):
                st.markdown(f'<div class="rp-row"><b>TPA → {esc(config.city(r))}</b>'
                            f'<span class="muted">{aircraft_label(f) if f and f.get("aircraft_type") else "—"}</span>'
                            f'<span class="muted">{esc(status)}</span>'
                            f'<span class="num">{price} <b>›</b></span></div>', unsafe_allow_html=True)
                if st.button(f"Search TPA to {config.city(r)}", key=f"routego_{code}_{r}"):
                    search_route(r, ss.get("airline_trip", "Round-trip") == "Round-trip")
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
                    + headline_html(cp, _unit(f))
                    + f'<div class="v3-route"><span class="fc-route">{route_label(f)}</span></div>'
                    + f'<div class="fc-meta">{fare_meta(f)}</div>'
                    + f'<div class="fc-line">{airline_label(f)} · {stops_label(f)}</div>'
                    + f'<div class="fc-line">Aircraft: {aircraft_label(f) or "Not listed"}</div>', unsafe_allow_html=True)
        bags_row(f, cp, key)
        with st.container(gap="small"):
            card_actions(f, f"mod_{key}", cabin=False)
            st.markdown('<div class="credit" style="margin:0">Opens Google Flights to confirm the fare.</div>',
                        unsafe_allow_html=True)


def deal_cards(code, deals):
    """Cheapest flight / Nonstop flight / Cheapest nonstop flight. An empty slot keeps its box with a placeholder."""
    s = search_state()
    party = party_of(s)
    carry, checked = s["carry_on"], s["checked"]
    for col, (slot, tag, note, empty) in zip(st.columns(3, gap="small"), DEAL_SLOTS):
        with col:
            f = deals[slot]
            key = f"{slot}_{code}"
            if f:
                _deal_tile(key, tag, note, f, pricing.card_price(f, carry, checked, party, bool(carry or checked)),
                           highlight=slot == "cheapest_nonstop")
            else:
                _empty_module(key, tag, empty, "Check back soon or search another date in Ascend Search.")
