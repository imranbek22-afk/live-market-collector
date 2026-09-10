"""
fetch.py — HTTP download of daily OHLCV from Stooq free CSV API.

What an interviewer might ask
-----------------------------
- "How do you handle rate limits and flaky networks?"
  Timeouts, status-code checks, exponential backoff with jitter on 429/5xx,
  and clear logging so failures are visible in demos.
- "Why requests + pandas instead of a finance SDK?"
  Keeps the HTTP call visible and interview-explainable; no opaque client.
- "What does the Stooq URL look like?"
  https://stooq.com/q/d/l/?s=aapl.us&i=d  (symbol + daily interval)
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from io import StringIO
from typing import Iterable

import pandas as pd
import requests

logger = logging.getLogger(__name__)

STOOQ_DAILY_URL_DEFAULT = "https://stooq.com/q/d/l/?s={symbol}&i=d"


def _url_template() -> str:
    """Allow STOOQ_URL_TEMPLATE override (e.g. local mock for offline CI)."""
    import os
    return os.getenv("STOOQ_URL_TEMPLATE", STOOQ_DAILY_URL_DEFAULT)
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2.0

# Canonical column names after normalize
SCHEMA_COLS = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "collected_at",
]


class FetchError(Exception):
    """Raised when a single-ticker fetch fails after retries."""


def _stooq_symbol_to_ticker(symbol: str) -> str:
    """aapl.us -> AAPL; spy.us -> SPY."""
    base = symbol.strip().lower().split(".")[0]
    return base.upper()


def fetch_stooq_csv(
    symbol: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """
    Download daily OHLCV CSV for one Stooq symbol and return a normalized DataFrame.

    Real HTTP GET — visible for demos / interviews.
    Schema: ticker, date, open, high, low, close, volume, source, collected_at
    """
    url = _url_template().format(symbol=symbol.strip().lower())
    sess = session or requests.Session()
    last_err: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("GET %s (attempt %d/%d)", url, attempt, max_retries)
            resp = sess.get(url, timeout=timeout)

            if resp.status_code == 429:
                sleep_s = backoff_base ** attempt + random.uniform(0, 0.5)
                logger.warning(
                    "Rate limited (429) for %s; sleeping %.1fs", symbol, sleep_s
                )
                time.sleep(sleep_s)
                continue

            if resp.status_code >= 500:
                sleep_s = backoff_base ** attempt + random.uniform(0, 0.5)
                logger.warning(
                    "Server error %s for %s; sleeping %.1fs",
                    resp.status_code,
                    symbol,
                    sleep_s,
                )
                time.sleep(sleep_s)
                continue

            if resp.status_code != 200:
                raise FetchError(
                    f"Non-200 response for {symbol}: HTTP {resp.status_code}"
                )

            text = resp.text.strip()
            if (
                not text
                or text.lower().startswith("<!doctype")
                or "<html" in text.lower()
            ):
                raise FetchError(
                    f"Empty or HTML response for {symbol} (blocked/malformed)"
                )

            # Stooq CSV header: Date,Open,High,Low,Close,Volume
            raw = pd.read_csv(StringIO(text))
            if raw.empty:
                raise FetchError(f"Empty CSV body for {symbol}")

            rename = {c: c.strip().lower() for c in raw.columns}
            raw = raw.rename(columns=rename)
            required = {"date", "open", "high", "low", "close", "volume"}
            missing = required - set(raw.columns)
            if missing:
                raise FetchError(
                    f"Malformed CSV for {symbol}: missing columns {sorted(missing)}"
                )

            collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ticker = _stooq_symbol_to_ticker(symbol)

            out = pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": pd.to_datetime(raw["date"]).dt.strftime("%Y-%m-%d"),
                    "open": pd.to_numeric(raw["open"], errors="coerce"),
                    "high": pd.to_numeric(raw["high"], errors="coerce"),
                    "low": pd.to_numeric(raw["low"], errors="coerce"),
                    "close": pd.to_numeric(raw["close"], errors="coerce"),
                    "volume": pd.to_numeric(raw["volume"], errors="coerce"),
                    "source": "stooq",
                    "collected_at": collected_at,
                }
            )
            before = len(out)
            out = out.dropna(subset=["open", "high", "low", "close"])
            if out.empty:
                raise FetchError(f"All rows malformed for {symbol}")
            if len(out) < before:
                logger.warning(
                    "Dropped %d malformed rows for %s", before - len(out), symbol
                )

            out = out[SCHEMA_COLS].sort_values("date").reset_index(drop=True)
            logger.info("Fetched %d rows for %s (%s)", len(out), ticker, symbol)
            return out

        except requests.Timeout as exc:
            last_err = exc
            sleep_s = backoff_base ** attempt + random.uniform(0, 0.5)
            logger.warning("Timeout for %s; sleeping %.1fs", symbol, sleep_s)
            time.sleep(sleep_s)
        except requests.RequestException as exc:
            last_err = exc
            sleep_s = backoff_base ** attempt + random.uniform(0, 0.5)
            logger.warning(
                "Request error for %s: %s; sleeping %.1fs", symbol, exc, sleep_s
            )
            time.sleep(sleep_s)
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(f"Failed to parse Stooq CSV for {symbol}: {exc}") from exc

    raise FetchError(
        f"Failed to fetch {symbol} after {max_retries} attempts: {last_err}"
    )


def fetch_many(
    symbols: Iterable[str],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    pause_between: float = 0.5,
) -> pd.DataFrame:
    """
    Fetch several symbols; concatenate into one DataFrame.
    Continues on per-ticker failure (logs error) so one bad symbol doesn't abort all.
    """
    symbol_list = [s.strip() for s in symbols if s and str(s).strip()]
    frames: list[pd.DataFrame] = []
    sess = requests.Session()
    sess.headers.update(
        {"User-Agent": "live-market-collector/0.1 (student portfolio; educational)"}
    )

    for i, symbol in enumerate(symbol_list):
        try:
            df = fetch_stooq_csv(
                symbol,
                timeout=timeout,
                max_retries=max_retries,
                backoff_base=backoff_base,
                session=sess,
            )
            frames.append(df)
        except FetchError as exc:
            logger.error("Skipping %s: %s", symbol, exc)
        if pause_between and i < len(symbol_list) - 1:
            time.sleep(pause_between)

    if not frames:
        raise FetchError("No tickers fetched successfully")
    return pd.concat(frames, ignore_index=True)
