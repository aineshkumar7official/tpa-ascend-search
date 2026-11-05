"""Rolling search windows, recomputed each run from "today" in America/New_York."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.config import settings

FRI, TUE = 4, 1

# window_id -> (weekday to depart, weeks out, days until return)
WINDOWS = {
    "wkend+2": (FRI, 2, 2),   # Friday ~2 weeks out, back Sunday
    "mid+4":   (TUE, 4, 7),   # Tuesday ~4 weeks out, back Tuesday +7
    "wkend+6": (FRI, 6, 3),   # Friday ~6 weeks out, back Monday
}


def today_local():
    return datetime.now(ZoneInfo(settings.TIMEZONE)).date()


def _next_weekday_on_or_after(d, weekday):
    return d + timedelta(days=(weekday - d.weekday()) % 7)


def window_dates(window_id, today=None):
    today = today or today_local()
    weekday, weeks, stay = WINDOWS[window_id]
    depart = _next_weekday_on_or_after(today + timedelta(weeks=weeks), weekday)
    return depart, depart + timedelta(days=stay)


def windows(today=None):
    """[{'window_id', 'depart', 'return'}] with ISO date strings."""
    out = []
    for wid in WINDOWS:
        depart, ret = window_dates(wid, today)
        out.append({"window_id": wid, "depart": depart.isoformat(), "return": ret.isoformat()})
    return out


def parse(d):
    return d if isinstance(d, date) else date.fromisoformat(d)
