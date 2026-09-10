"""
schedule.py — On-demand job runner + simple interval schedule (APScheduler).

What an interviewer might ask
-----------------------------
- "Fetch on demand vs schedule — why both?"
  Interviews often ask for a one-shot CLI demo AND how you'd productionize
  collection. Interval schedule is the bridge without needing cron/K8s.
- "Why APScheduler instead of cron?"
  Pure-Python, works cross-platform in a student laptop demo; BlockingScheduler
  keeps the process alive and logs clearly.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


def run_collect_job(job_fn: Callable[[], None], label: str = "collect") -> None:
    """
    Execute one collection cycle with timing + error boundary.
    job_fn should fetch -> store -> trends (wired in cli).
    """
    t0 = time.perf_counter()
    logger.info("=== job start: %s ===", label)
    try:
        job_fn()
        elapsed = time.perf_counter() - t0
        logger.info("=== job ok: %s (%.2fs) ===", label, elapsed)
    except Exception:
        elapsed = time.perf_counter() - t0
        logger.exception("=== job FAILED: %s (%.2fs) ===", label, elapsed)
        raise


def start_interval_schedule(
    job_fn: Callable[[], None],
    interval_seconds: int = 3600,
    *,
    run_immediately: bool = True,
) -> None:
    """
    Blocking interval schedule via APScheduler.
    Ctrl+C to stop. Suitable for local demos / insight-week laptops.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    if interval_seconds < 60:
        logger.warning(
            "interval_seconds=%d is aggressive for free HTTP APIs; "
            "consider >= 300 for demos",
            interval_seconds,
        )

    scheduler = BlockingScheduler()

    def _wrapped() -> None:
        try:
            run_collect_job(job_fn, label="scheduled-collect")
        except Exception:
            # Don't crash the scheduler on one failure
            logger.error("Scheduled job error swallowed so schedule continues")

    if run_immediately:
        logger.info("Running first collect immediately before schedule loop")
        _wrapped()

    scheduler.add_job(
        _wrapped,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="live_market_collect",
        name="Stooq OHLCV collect",
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Scheduler started: every %d seconds. Press Ctrl+C to stop.",
        interval_seconds,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user")
