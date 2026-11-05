
from core import config
from core.experience import flight_score, rank_bundles


def _f(airline, price_dur, amen=None, stars=None, n=0, aircraft="A321"):
    price, dur = price_dur
    return {"airline_iata": airline, "price_usd": price, "duration_min": dur, "aircraft_type": aircraft,
            "amenities": amen or {}, "review": {"stars_5": stars, "review_count": n} if stars else None}


def test_unknowns_get_half_credit_and_flag():
    s = flight_score(_f("DL", (100, 90)), shortest_min=90)
    assert s.total == 6.5 and not s.complete    # comfort 1.5 (half of 3) + 0.5 legroom, reviews 1.5, time 3
    full = flight_score(_f("DL", (100, 90), {"wifi": True, "seatback_screen": True, "stream_to_device": True,
                                           "power": True, "legroom_pitch_in": "32"}, 5.0, 10), 90)
    assert full.total == 10.0 and full.complete


def test_time_penalty():
    assert flight_score(_f("DL", (100, 150)), shortest_min=90).time == 2.0   # +60 min


def test_rank_bundles_tags_and_mixed_filter():
    out_dl, out_b6 = _f("DL", (0, 100)), _f("B6", (0, 90))
    bundles = [{"out": out_dl, "ret": _f("DL", (0, 100)), "total": 300},
               {"out": out_dl, "ret": _f("DL", (0, 130)), "total": 250},
               {"out": out_b6, "ret": _f("DL", (0, 95)), "total": 200}]
    ranked = rank_bundles(bundles)                         # mixed-airline bundle filtered out
    assert len(ranked) == 2
    assert "Lowest price" in next(b for b in ranked if b["total"] == 250)["tags"]
    assert "Shortest travel time" in next(b for b in ranked if b["total"] == 300)["tags"]
    assert len(rank_bundles(bundles, allow_mixed=True)) == 3


def test_destinations_import_shape():
    d = {x["iata"]: x for x in config.destinations()}
    assert len(d) >= 100
    assert d["CUN"]["carrier_status"]["MX"]["status"] == "coming_soon" and d["CUN"]["status"] == "current"
    assert d["ZRH"]["status"] == "suspending"
    assert all(x["status"] == "current" for x in d.values() if x["scan"])
    assert "code_note" in d["TKI"]


def test_parse_status():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("imp", Path(__file__).parent.parent / "scripts" / "import_destinations_docx.py")
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.parse_status("Coming soon — Nov 20, 2026") == ("coming_soon", "Nov 20, 2026")
    assert mod.parse_status("Current") == ("current", None)
    assert mod.parse_status("Suspending — Suspended from January 2027") == ("suspending", "Suspended from January 2027")
    assert mod.clean_code("TKI*") == "TKI" and mod.clean_code("IAD†") == "IAD"
