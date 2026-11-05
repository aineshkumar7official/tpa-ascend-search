"""Run the background cycle every SCAN_INTERVAL_HOURS and refresh news daily.

The first scan is due SCAN_INTERVAL_HOURS after the last one in price_history (immediately if overdue),
so restarts don't cause extra scans. Runs missed while the Mac slept fire once on wake
(misfire_grace_time=None + coalesce) instead of being skipped.
"""
import _path  # noqa: F401

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from bots.pipeline import refresh_news, run_background_cycle
from core.config import settings
from core.db import get_conn


def first_run_time(hours):
    row = get_conn().execute("SELECT MAX(scanned_at) FROM price_history").fetchone()
    now = datetime.now(timezone.utc)
    if not row or not row[0]:
        return now
    due = datetime.fromisoformat(row[0]) + timedelta(hours=hours)
    return max(due, now)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("primp").setLevel(logging.WARNING)
    hours = settings.SCAN_INTERVAL_HOURS
    sched = BlockingScheduler(job_defaults={"misfire_grace_time": None, "coalesce": True, "max_instances": 1})
    start = first_run_time(hours)
    sched.add_job(run_background_cycle, "interval", hours=hours, next_run_time=start, id="scan_cycle")
    sched.add_job(refresh_news, "cron", hour=7, minute=5, id="news_daily")
    logging.info("Scheduler started: every %dh, next scan %s", hours, start.astimezone().isoformat(timespec="minutes"))
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
