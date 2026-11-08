"""The fare options Google Flights lists for one exact flight (Basic Economy $160, Economy $220, ...).

Google loads these on its booking page behind a browser-only request, so we open that page in local Chrome
and read what it shows. Slow (2-5 s), so results are cached and fetched one at a time. Everything here is
best effort: no Chrome, a changed page or an airline with no list just means `options` is empty, and the app
falls back to the airline-wide fees in airline_policies.json.

Some airlines (Sun Country, Avelo, Porter, Avianca, Copa, Cayman) show Google only one price with no list;
that price is kept as `airline_price`.
"""
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from core import booking
from core.config import settings
from core.db import cache_get, cache_set, get_conn, utcnow

log = logging.getLogger(__name__)

FOUND_MAX_AGE_DAYS = 0.25    # 6 hours: fares move, and these prices replace the scanned one on cards
EMPTY_MAX_AGE_DAYS = 1 / 24  # retry sooner when the page failed
MAX_QUEUED = 40

_PRICE = re.compile(r"^\$([\d,]+)$")
_BAG_FEE = re.compile(r"^1st checked bag(?: per passenger)?: \$([\d,]+)$")
_FREE_BAG = re.compile(r"^(?:1st checked bag free|[1-9] free checked bags?)(?: per passenger)?$")
_DROP = re.compile(r"^(Continue|(?:First|Second) checked bag costs .*)$")
_END = ("Fare and baggage", "Book with ", "Prices include", "For non-refundable")


def _money(text):
    return float(text.replace(",", ""))


def _option(name, price, raw):
    """`first_bag`: $ for the 1st checked bag per passenger, for the whole trip (Google doubles it on a round trip);
    0 when one is included; None when Google gives no amount. `carry_on`: "free", "fee", "none" or None."""
    lines, first_bag, carry = [], None, None
    for line in raw:
        if _DROP.match(line):
            continue
        fee = _BAG_FEE.match(line)
        if fee:
            first_bag = _money(fee.group(1))
            line = line.replace(":", "")
        elif _FREE_BAG.match(line):
            first_bag = 0.0
        low = line.lower()
        if "carry-on" in low:
            carry = "none" if low.startswith("no ") else "fee" if "for a fee" in low else "free" if "free" in low else carry
        lines.append(line)
    return {"name": name, "price": price, "lines": lines, "first_bag": first_bag, "carry_on": carry}


def _airline_row(body):
    """Index of 'Book with X' on the row Google tags 'Airline'. Agencies can quote other prices and rules."""
    for i, line in enumerate(body):
        if line.startswith("Book with ") and (line.endswith("Airline") or (i + 1 < len(body) and body[i + 1] == "Airline")):
            return i
    return None


def parse(text):
    """Read Google's rendered booking page into {airline, airline_price, options (cheapest first)}."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    start = next((i for i, ln in enumerate(lines) if ln == "Booking options"), None)
    out = {"airline": None, "airline_price": None, "options": []}
    if start is None:
        return out
    body = lines[start + 1:]
    row = _airline_row(body)
    if row is None:
        return out
    out["airline"] = re.sub(r"\s*Airline$", "", body[row][len("Book with "):])

    section = []
    for line in body[row + 1:]:
        if line.startswith(_END):
            break
        section.append(line)
    opts, name, price, raw = [], None, None, []
    for i, line in enumerate(section):
        following = section[i + 1] if i + 1 < len(section) else ""
        if _PRICE.match(following) and not _PRICE.match(line) and line not in ("from", "Airline", "Hide options"):
            if name:
                opts.append(_option(name, price, raw))
            name, price, raw = line, _money(following[1:]), []
        elif name and not _PRICE.match(line):
            raw.append(line)
    if name:
        opts.append(_option(name, price, raw))
    out["options"] = sorted(opts, key=lambda o: o["price"])
    first_price = next((_money(ln[1:]) for ln in section if _PRICE.match(ln)), None)
    out["airline_price"] = out["options"][0]["price"] if out["options"] else first_price
    return out


def cheapest(data):
    """The option Google's headline price buys, or None when it lists no options."""
    options = (data or {}).get("options") or []
    return options[0] if options else None


def price(data):
    """What Google charges through the airline for this flight, or None."""
    return (data or {}).get("airline_price")


def upgrades(data):
    """Dearer options with what changes: [{name, price, extra, changes}]. `changes` drops what the cheapest fare has."""
    base = cheapest(data)
    if not base:
        return []
    have = set(base["lines"])
    return [{"name": o["name"], "price": o["price"], "extra": o["price"] - base["price"],
             "changes": [ln for ln in o["lines"] if ln not in have]} for o in data["options"][1:]]


def rules(option, *words):
    """The option's lines mentioning any of `words`, in Google's wording."""
    return [ln for ln in (option or {}).get("lines", []) if any(w in ln.lower() for w in words)]


def lookable(fare, return_fare=None):
    """Google only lists fare options once every flight is picked, so a round trip needs its return."""
    if fare.get("return_date") and not return_fare:
        return False
    return bool(booking.encode(fare, 1, return_fare))


def _flights(fare):
    return ",".join(s.get("flight") or "" for s in booking.segments(fare)) or fare.get("flight_numbers") or ""


def cache_key(fare, party, return_fare=None):
    from core.pricing import Party

    p = Party.coerce(party)
    back = _flights(return_fare) if return_fare else ""
    return (f"fare_options|{_flights(fare)}|{fare.get('depart_date')}|{back}|{fare.get('return_date') or ''}"
            f"|{p.adults}.{p.children}.{p.infants}")


def cached(conn, fare, party, return_fare=None):
    """(hit, data) from the cache. A failed lookup expires sooner, so the next view tries again."""
    key = cache_key(fare, party, return_fare)
    hit, data = cache_get(conn, key, FOUND_MAX_AGE_DAYS)
    if hit and (data or {}).get("error"):
        hit, data = cache_get(conn, key, EMPTY_MAX_AGE_DAYS)
    return hit, data


def available():
    if settings.FARE_OPTIONS != "on":
        return False
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _render(url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_context(locale="en-US").new_page()
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # The airline row appears once Google's booking request returns.
            page.get_by_text("Prices include required taxes").first.wait_for(timeout=15000)
            return page.inner_text("body")
        finally:
            browser.close()


def fetch(fare, party, return_fare=None):
    return {**parse(_render(booking.book_url(fare, party, return_fare))), "checked_at": utcnow()}


def lookup(conn, fare, party, return_fare=None):
    """Cached fare options, fetching on a miss. None when they can't be looked up."""
    hit, data = cached(conn, fare, party, return_fare)
    if hit:
        return data
    if not available() or not lookable(fare, return_fare):
        return None
    try:
        data = fetch(fare, party, return_fare)
    except Exception as e:  # noqa: BLE001 - no Chrome, timeouts, blocked page: fall back to airline-wide fees
        log.warning("fare options failed for %s: %s", fare.get("flight_numbers"), e)
        data = {"airline": None, "airline_price": None, "options": [], "checked_at": utcnow(), "error": str(e)[:200]}
    cache_set(conn, cache_key(fare, party, return_fare), data)
    return data


_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fare-options")
_queued = set()
_lock = threading.Lock()


def enqueue(fare, party, return_fare=None):
    """Look this fare up in the background, one at a time, so cards render without waiting on a browser."""
    if not available() or not lookable(fare, return_fare):
        return
    key = cache_key(fare, party, return_fare)
    with _lock:
        if key in _queued or len(_queued) >= MAX_QUEUED:
            return
        _queued.add(key)

    def job():
        conn = get_conn()
        try:
            lookup(conn, fare, party, return_fare)
        except Exception as e:  # noqa: BLE001 - never kill the worker
            log.warning("background fare options failed: %s", e)
        finally:
            conn.close()
            with _lock:
                _queued.discard(key)

    _worker.submit(job)
