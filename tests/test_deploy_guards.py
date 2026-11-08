"""Quota protection for the free deployment: scan fallback to SerpApi, live-search daily cap, database sync switch."""
import pytest

from bots import pipeline
from bots.scouter import BLOCKED_AFTER, FallbackSearch
from core import remote_db
from core.config import settings
from sources import flights_fast, flights_serpapi

PLAN = {("ATL", "2026-12-04"), ("JFK", "2026-12-04")}


def _blocked(*a, **k):
    raise flights_fast.SearchFailed("blocked")


@pytest.fixture
def serp_on(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "test")
    monkeypatch.setattr(settings, "SERPAPI_MONTHLY_BUDGET", 200)
    monkeypatch.setattr(settings, "SERPAPI_RESERVE", 50)
    monkeypatch.setattr(settings, "SERPAPI_SCAN_DAILY", 2)


def _search(conn, calls):
    def serp(*a, **k):
        flights_serpapi.spend(conn)  # what flights_serpapi.search does for each real call
        calls.append(a)
        return [{"stops": 0}]
    return FallbackSearch(conn, fast=_blocked, serp=serp, plan=PLAN)


def test_fast_flights_used_while_it_works(conn, serp_on):
    calls = []
    s = FallbackSearch(conn, fast=lambda *a, **k: ["ok"], serp=lambda *a, **k: calls.append(a), plan=PLAN)
    assert s("TPA", "ATL", "2026-12-04") == ["ok"] and not calls


def test_serpapi_only_after_repeated_failures_and_only_for_the_plan(conn, serp_on):
    calls = []
    s = _search(conn, calls)
    for _ in range(BLOCKED_AFTER - 1):
        with pytest.raises(flights_fast.SearchFailed):
            s("TPA", "ATL", "2026-12-04")
    assert not calls                                      # a couple of failures don't count as blocked
    assert s("TPA", "ATL", "2026-12-04") == [{"stops": 0}]  # the 3rd failure switches to SerpApi
    with pytest.raises(flights_fast.SearchFailed):
        s("TPA", "BOS", "2026-12-04")                     # not in the fallback plan: nothing spent
    with pytest.raises(flights_fast.SearchFailed):
        s("TPA", "ATL", "2026-12-04", nonstop=False)      # any-stops searches never use SerpApi
    assert len(calls) == 1


def test_serpapi_daily_allowance(conn, serp_on):
    calls = []
    s = _search(conn, calls)
    s.blocked = True
    s("TPA", "ATL", "2026-12-04")
    s("TPA", "JFK", "2026-12-04", "2026-12-07")
    with pytest.raises(flights_fast.SearchFailed):
        s("TPA", "ATL", "2026-12-04", "2026-12-07")       # SERPAPI_SCAN_DAILY = 2
    assert len(calls) == 2


def test_serpapi_never_touches_the_reserve(conn, serp_on):
    for _ in range(150):
        flights_serpapi.spend(conn)                       # 150 of 200 used: only the 50 reserve is left
    calls = []
    s = _search(conn, calls)
    s.blocked = True
    with pytest.raises(flights_fast.SearchFailed):
        s("TPA", "ATL", "2026-12-04")
    assert not calls


def test_no_serpapi_without_a_key(conn, serp_on, monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "")
    calls = []
    s = _search(conn, calls)
    s.blocked = True
    with pytest.raises(flights_fast.SearchFailed):
        s("TPA", "ATL", "2026-12-04")
    assert not calls


def test_live_search_daily_cap(conn, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_SEARCH_DAILY_CAP", 2)
    monkeypatch.setattr(pipeline, "_live_used", {})
    monkeypatch.setattr(flights_fast, "search", lambda *a, **k: [])
    assert pipeline.live_search(conn, "TPA", "ATL", "2026-12-04")[2] is None
    assert pipeline.live_search(conn, "TPA", "ATL", "2026-12-04")[2] is None
    fares, source, error = pipeline.live_search(conn, "TPA", "ATL", "2026-12-04")
    assert fares == [] and error == pipeline.LIVE_CAP_MESSAGE


def test_live_search_never_spends_serpapi_when_off(conn, monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "test")
    monkeypatch.setattr(settings, "LIVE_SERPAPI", "off")
    monkeypatch.setattr(flights_fast, "search", _blocked)
    monkeypatch.setattr(flights_serpapi, "search", lambda *a, **k: pytest.fail("SerpApi was called"))
    fares, source, error = pipeline.live_search(conn, "TPA", "ATL", "2026-12-04")
    assert fares == [] and error


def test_database_sync_is_off_without_settings(monkeypatch):
    monkeypatch.setattr(settings, "DATA_REPO", "")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    assert not remote_db.enabled() and remote_db.sync() is None


def test_sync_reapplies_the_database_after_a_reload(monkeypatch, tmp_path):
    """Streamlit reloads changed modules on deploy and settings.DB_PATH goes back to the empty default. The next page
    load must point it at the downloaded database again, without waiting for the 10-minute check."""
    monkeypatch.setattr(settings, "DATA_REPO", "me/repo")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "t")
    monkeypatch.setattr(settings, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(remote_db, "_state", {"checked_at": 0.0, "path": None, "sha": None})
    calls = []
    monkeypatch.setattr(remote_db, "latest_sha", lambda: calls.append(1) or "abc123def4567890")
    monkeypatch.setattr(remote_db, "_download", lambda sha, dest: dest.write_bytes(b"db"))
    assert remote_db.sync() == "abc123def4567890"
    downloaded = settings.DB_PATH
    assert downloaded.endswith("ascend-abc123def456.db")
    monkeypatch.setattr(settings, "DB_PATH", "data/ascend.db")   # what a module reload does
    assert remote_db.sync() == "abc123def4567890" and settings.DB_PATH == downloaded
    assert len(calls) == 1                                        # no extra GitHub call within 10 minutes


def test_sync_failure_is_retried_and_explained(monkeypatch, tmp_path):
    import requests

    monkeypatch.setattr(settings, "DATA_REPO", "me/repo")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "bad")
    monkeypatch.setattr(remote_db, "_state", {"checked_at": 0.0, "path": None, "sha": None})
    resp = requests.Response()
    resp.status_code = 401

    def fail():
        raise requests.HTTPError(response=resp)
    monkeypatch.setattr(remote_db, "latest_sha", fail)
    assert remote_db.sync() is None and "401" in remote_db.status()
    assert remote_db._state["checked_at"] == 0.0                 # tries again on the next page load
