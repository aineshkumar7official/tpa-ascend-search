"""Deployed app only: keep the price database in step with the `data` branch the scan workflow writes.

The GitHub Actions scan (.github/workflows/scan.yml) pushes `ascend.db.gz` to the `data` branch as a single commit.
When DATA_REPO and GITHUB_TOKEN are set (Streamlit Cloud secrets), the app checks that branch's latest commit at most
every few minutes and, when it changed, downloads the database to a new file named after the commit and points
settings.DB_PATH at it. The file in use is never overwritten, so open connections keep working; older copies are
deleted. Locally (no DATA_REPO) this does nothing and the app uses data/ascend.db as before.
"""
import gzip
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

import requests

from core.config import settings

log = logging.getLogger(__name__)

API = "https://api.github.com"
last_error = {"text": None}  # why the latest sync failed, shown when the app has no prices
FILE = "ascend.db.gz"


def enabled():
    return bool(settings.DATA_REPO and settings.GITHUB_TOKEN)


def _headers(accept):
    return {"Authorization": f"Bearer {settings.GITHUB_TOKEN}", "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "tpa-ascend-search"}


def latest_sha():
    """Commit sha at the tip of the data branch."""
    r = requests.get(f"{API}/repos/{settings.DATA_REPO}/commits/{settings.DATA_BRANCH}",
                     headers=_headers("application/vnd.github.sha"), timeout=20)
    r.raise_for_status()
    return r.text.strip()


def _download(sha, dest):
    r = requests.get(f"{API}/repos/{settings.DATA_REPO}/contents/{FILE}", params={"ref": sha},
                     headers=_headers("application/vnd.github.raw+json"), timeout=120, stream=True)
    r.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, dir=dest.parent, suffix=".gz") as tmp:
        for chunk in r.iter_content(1 << 20):
            tmp.write(chunk)
    try:
        with gzip.open(tmp.name, "rb") as src, open(f"{dest}.part", "wb") as out:
            shutil.copyfileobj(src, out)
        os.replace(f"{dest}.part", dest)
    finally:
        os.unlink(tmp.name)


def _cleanup(keep):
    """Delete older downloaded copies (and their WAL files), keeping the current and the one before it."""
    copies = sorted(keep.parent.glob("ascend-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in copies[2:]:
        for p in (old, Path(f"{old}-wal"), Path(f"{old}-shm")):
            p.unlink(missing_ok=True)


CHECK_EVERY = 600            # seconds between checks of the data branch
_state = {"checked_at": 0.0, "path": None, "sha": None}


def sync(force=False):
    """Point settings.DB_PATH at the newest scan. Checks GitHub at most every CHECK_EVERY seconds, but re-applies the
    downloaded path on every call: when Streamlit reloads changed modules after a deploy, settings goes back to its
    default (an empty database), and this puts it right on the next page load. Returns the commit sha in use, or None
    when sync is off or has never worked (the app then keeps using whatever database it already has)."""
    if not enabled():
        return None
    now = time.monotonic()
    if force or not _state["path"] or now - _state["checked_at"] >= CHECK_EVERY:
        _state["checked_at"] = now
        try:
            sha = latest_sha()
            dest = Path(settings.DB_DIR) / f"ascend-{sha[:12]}.db"
            if not dest.exists():
                log.info("downloading database for data commit %s", sha[:12])
                _download(sha, dest)
            _state.update(path=str(dest), sha=sha)
            _cleanup(dest)
            last_error["text"] = None
        except Exception as e:  # network, token or missing branch: keep serving the current data
            log.warning("database sync failed: %s", e)
            last_error["text"] = (f"GitHub said {e.response.status_code}: check GITHUB_TOKEN (read-only Contents on "
                                  f"{settings.DATA_REPO}) and DATA_REPO" if isinstance(e, requests.HTTPError)
                                  else f"{type(e).__name__}: {e}")
            if not _state["path"]:
                _state["checked_at"] = 0.0  # never worked yet: try again on the next page load
    if _state["path"]:
        settings.DB_PATH = _state["path"]
    return _state["sha"]


def status():
    """One line for operators when the app has no prices: is sync configured, and did it work?"""
    if not settings.DATA_REPO and not settings.GITHUB_TOKEN:
        return "Price data isn't connected: DATA_REPO and GITHUB_TOKEN aren't set in the app's secrets."
    if not enabled():
        return f"Price data isn't connected: {'GITHUB_TOKEN' if settings.DATA_REPO else 'DATA_REPO'} isn't set in the app's secrets."
    if last_error["text"]:
        return f"Price data couldn't be loaded ({last_error['text']})."
    return None
