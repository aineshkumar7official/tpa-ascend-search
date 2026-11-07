from bots import enricher
from core import queries


def test_matrix_curated_photos_without_database_assets(conn, monkeypatch):
    monkeypatch.setattr(enricher.config, "cabins", lambda: {
        "DL|*": {"seat": {"image_url": "/app/static/delta-seat.jpg", "credit": "Delta", "source_page": "https://delta.com"}}
    })
    result = queries.airline_photo_asset(conn, "DL")
    assert result["seat_url"] == "/app/static/delta-seat.jpg"
    assert result["seat_credit"] == "Delta"
    assert result["food_url"] is None


def test_missing_curated_slot_does_not_search_for_interior(monkeypatch):
    calls = []
    monkeypatch.setattr(enricher.config, "cabins", lambda: {})
    monkeypatch.setattr(enricher.config, "fleet", lambda: {})
    monkeypatch.setattr(enricher.commons, "search", lambda *args: calls.append(args) or None)
    asset = enricher.fetch_asset(None, "DL", "Airbus A321")
    assert asset["interior_url"] is None
    assert asset["seat_url"] is None
    assert asset["food_url"] is None
    assert len(calls) == 1
    assert calls[0][1] == "exterior"


def test_curated_slots_never_cross_airlines(monkeypatch):
    monkeypatch.setattr(enricher.config, "cabins", lambda: {
        "DL|*": {"seat": {"image_url": "delta-seat.jpg"}},
        "F9|*": {"seat": {"image_url": "frontier-seat.jpg"}},
    })
    assert enricher.curated_photos("F9")["seat_url"] == "frontier-seat.jpg"
    assert enricher.curated_photos("UA")["seat_url"] is None


def test_aircraft_prefix_does_not_select_different_cabin(monkeypatch):
    monkeypatch.setattr(enricher.config, "cabins", lambda: {
        "B6|Airbus A321neo": {"seat": {"image_url": "neo-seat.jpg"}},
    })
    assert enricher.curated_photos("B6", "Airbus A321")["seat_url"] is None
    assert enricher.curated_photos("B6", "Airbus A321neo")["seat_url"] == "neo-seat.jpg"
