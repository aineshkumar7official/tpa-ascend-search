from datetime import date

from core.dates import windows


def test_windows_from_a_thursday():
    w = {x["window_id"]: x for x in windows(today=date(2026, 10, 22))}  # Thursday
    assert w["wkend+2"] == {"window_id": "wkend+2", "depart": "2026-11-06", "return": "2026-11-08"}
    assert w["mid+4"] == {"window_id": "mid+4", "depart": "2026-11-24", "return": "2026-12-01"}
    assert w["wkend+6"] == {"window_id": "wkend+6", "depart": "2026-12-04", "return": "2026-12-07"}


def test_weekdays_always_right():
    for d in range(1, 29):
        w = {x["window_id"]: x for x in windows(today=date(2026, 2, d))}
        assert date.fromisoformat(w["wkend+2"]["depart"]).weekday() == 4
        assert date.fromisoformat(w["mid+4"]["depart"]).weekday() == 1
        assert date.fromisoformat(w["wkend+6"]["return"]).weekday() == 0
