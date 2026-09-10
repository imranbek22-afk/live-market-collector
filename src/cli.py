"""
cli.py — Entry point: python -m src.cli [fetch|run-once|schedule]

What an interviewer might ask
-----------------------------
- "Happy path needs no secrets — how?"
  Stooq free CSV HTTP; config via env/.env with sensible defaults.
- "Difference between fetch and run-once?"
  Same pipeline today; `fetch` is the explicit demo verb, `run-once` mirrors
  what the scheduler invokes (handy for scripts/CI).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Project root = parent of src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Optional .env — never required for happy path."""
    try:
        from dotenv import load_dotenv

        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _config() -> dict:
    _load_dotenv()
    tickers = os.getenv("TICKERS", "aapl.us,msft.us,spy.us")
    return {
        "symbols": [t.strip() for t in tickers.split(",") if t.strip()],
        "db_path": PROJECT_ROOT / os.getenv("DB_PATH", "data/market.db"),
        "csv_dir": PROJECT_ROOT / os.getenv("CSV_EXPORT_DIR", "data/exports"),
        "output_dir": PROJECT_ROOT / os.getenv("OUTPUT_DIR", "output"),
        "timeout": int(os.getenv("HTTP_TIMEOUT", "30")),
        "max_retries": int(os.getenv("MAX_RETRIES", "3")),
        "backoff_base": float(os.getenv("BACKOFF_BASE_SECONDS", "2")),
        "interval": int(os.getenv("SCHEDULE_INTERVAL_SECONDS", "3600")),
    }


def collect_pipeline(
    symbols: list[str] | None = None,
    *,
    skip_dashboard: bool = False,
) -> None:
    """Fetch -> SQLite upsert -> CSV export -> trends dashboard."""
    from .fetch import fetch_many
    from .store import export_csv, upsert_ohlcv, load_from_db
    from .trends import write_dashboard

    cfg = _config()
    syms = symbols or cfg["symbols"]
    logging.getLogger(__name__).info("Collecting: %s", ", ".join(syms))

    df = fetch_many(
        syms,
        timeout=cfg["timeout"],
        max_retries=cfg["max_retries"],
        backoff_base=cfg["backoff_base"],
    )
    n = upsert_ohlcv(df, cfg["db_path"])
    csv_path = export_csv(df, cfg["csv_dir"], append=True)
    logging.getLogger(__name__).info("SQLite rows upserted=%d  CSV=%s", n, csv_path)

    if not skip_dashboard:
        # Prefer full DB history for MA windows (CSV append alone may be partial)
        hist = load_from_db(cfg["db_path"])
        dash = write_dashboard(hist, cfg["output_dir"])
        logging.getLogger(__name__).info("Dashboard: %s", dash)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description=(
            "live-market-collector — Stooq OHLCV fetch, SQLite/CSV store, "
            "trend dashboard. No API key required."
        ),
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG logging",
    )
    common.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Override TICKERS, e.g. aapl.us,msft.us",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG logging",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Override TICKERS, e.g. aapl.us,msft.us",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser(
        "fetch", parents=[common], help="Fetch once, store, write dashboard"
    )
    p_fetch.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Skip trends dashboard",
    )

    p_once = sub.add_parser(
        "run-once",
        parents=[common],
        help="Same as fetch (scheduler-compatible alias)",
    )
    p_once.add_argument("--no-dashboard", action="store_true")

    p_sched = sub.add_parser(
        "schedule",
        parents=[common],
        help="Run collect on an interval (APScheduler; Ctrl+C to stop)",
    )
    p_sched.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Seconds between runs (default SCHEDULE_INTERVAL_SECONDS or 3600)",
    )
    p_sched.add_argument(
        "--no-immediate",
        action="store_true",
        help="Do not run once before entering the schedule loop",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    cfg = _config()
    symbols = (
        [t.strip() for t in args.tickers.split(",") if t.strip()]
        if args.tickers
        else None
    )

    if args.command in ("fetch", "run-once"):
        from .schedule import run_collect_job

        def job() -> None:
            collect_pipeline(symbols, skip_dashboard=args.no_dashboard)

        run_collect_job(job, label=args.command)
        return 0

    if args.command == "schedule":
        from .schedule import start_interval_schedule

        interval = args.interval if args.interval is not None else cfg["interval"]

        def job() -> None:
            collect_pipeline(symbols, skip_dashboard=False)

        start_interval_schedule(
            job,
            interval_seconds=interval,
            run_immediately=not args.no_immediate,
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
