from core import config
from core.ui import logo_tile


def test_every_listed_airline_gets_a_google_flights_logo():
    for code in config.airlines():
        assert config.logo_url(code) == f"https://www.gstatic.com/flights/airline_logos/70px/{code}.png"


def test_known_airline_renders_logo_image():
    html = logo_tile({"airline_iata": "DL"})
    assert '<img class="logo-img"' in html
    assert "airline_logos/70px/DL.png" in html


def test_logo_from_search_result_wins():
    html = logo_tile({"airline_iata": "DL", "logo_url": "https://example.com/dl.png"})
    assert "https://example.com/dl.png" in html
    assert "gstatic" not in html


def test_unknown_airline_keeps_monogram_tile():
    # gstatic answers 200 with a placeholder for unknown codes, so they must not get a URL.
    assert config.logo_url("ZZ") is None
    html = logo_tile({"airline_iata": "ZZ"})
    assert 'class="logo-tile"' in html and ">ZZ<" in html
    assert 'class="logo-tile"' in logo_tile({})
