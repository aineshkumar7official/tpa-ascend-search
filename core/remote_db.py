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
from pathlib import Path

import requests

from core.config import settings

log = logging.getLogger(__name__)

API = "https://api.github.com"
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


def sync():
    """Point settings.DB_PATH at the newest scan. Returns the commit sha in use, or None when sync is off or failed
    (the app then keeps using whatever database it already has)."""
    if not enabled():
        return None
    try:
        sha = latest_sha()
        dest = Path(settings.DB_DIR) / f"ascend-{sha[:12]}.db"
        if not dest.exists():
            log.info("downloading database for data commit %s", sha[:12])
            _download(sha, dest)
        settings.DB_PATH = str(dest)
        _cleanup(dest)
        return sha
    except Exception as e:  # network, token or missing branch: keep serving the current data
        log.warning("database sync failed: %s", e)
        return None
