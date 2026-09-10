"""
store.py — Persist OHLCV to SQLite (primary) and append/export CSV.

What an interviewer might ask
-----------------------------
- "Why SQLite as primary store?"
  Zero-ops, single file, SQL queryable — perfect for a portfolio demo.
  CSV is the portable export for Excel / sibling equity-stats-lab.
- "How do you avoid duplicate bars?"
  UNIQUE(ticker, date) + INSERT OR REPLACE (upsert by trading day).
- "Why UTC collected_at?"
  Unambiguous audit trail across timezones (demo runs in UTC on servers).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from .fetch import SCHEMA_COLS

logger = logging.getLogger(__name__)

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker       TEXT NOT NULL,
    date         TEXT NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       REAL,
    source       TEXT NOT NULL DEFAULT 'stooq',
    collected_at TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
"""

UPSERT_SQL = """
INSERT INTO ohlcv
    (ticker, date, open, high, low, close, volume, source, collected_at)
VALUES
    (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ticker, date) DO UPDATE SET
    open=excluded.open,
    high=excluded.high,
    low=excluded.low,
    close=excluded.close,
    volume=excluded.volume,
    source=excluded.source,
    collected_at=excluded.collected_at;
"""


def ensure_db(db_path: str | Path) -> Path:
    """Create parent dirs + ohlcv table if missing."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(CREATE_SQL)
        conn.commit()
    finally:
        conn.close()
    logger.debug("SQLite ready at %s", path)
    return path


def upsert_ohlcv(df: pd.DataFrame, db_path: str | Path) -> int:
    """
    Upsert rows into SQLite. Returns number of rows written.
    Expects SCHEMA_COLS columns.
    """
    if df is None or df.empty:
        logger.warning("upsert_ohlcv called with empty DataFrame")
        return 0

    missing = [c for c in SCHEMA_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing columns: {missing}")

    path = ensure_db(db_path)
    rows = [
        (
            str(r.ticker),
            str(r.date),
            float(r.open) if pd.notna(r.open) else None,
            float(r.high) if pd.notna(r.high) else None,
            float(r.low) if pd.notna(r.low) else None,
            float(r.close) if pd.notna(r.close) else None,
            float(r.volume) if pd.notna(r.volume) else None,
            str(r.source),
            str(r.collected_at),
        )
        for r in df[SCHEMA_COLS].itertuples(index=False)
    ]
    conn = sqlite3.connect(path)
    try:
        conn.executemany(UPSERT_SQL, rows)
        conn.commit()
    finally:
        conn.close()
    logger.info("Upserted %d rows into %s", len(rows), path)
    return len(rows)


def export_csv(
    df: pd.DataFrame,
    export_dir: str | Path,
    *,
    filename: str | None = None,
    append: bool = True,
) -> Path:
    """
    Write/append CSV under data/exports/.
    Default filename: market_ohlcv.csv (combined). Per-ticker files optional via filename=.
    """
    if df is None or df.empty:
        raise ValueError("Cannot export empty DataFrame")

    out_dir = Path(export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / (filename or "market_ohlcv.csv")

    write_df = df[SCHEMA_COLS].copy()
    if append and path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, write_df], ignore_index=True)
        # Dedupe by ticker+date keeping last (latest collected_at typically last)
        combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
        combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
        combined.to_csv(path, index=False)
        logger.info("Appended/deduped CSV -> %s (%d rows)", path, len(combined))
    else:
        write_df.sort_values(["ticker", "date"]).to_csv(path, index=False)
        logger.info("Wrote CSV -> %s (%d rows)", path, len(write_df))
    return path


def load_from_db(
    db_path: str | Path,
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    """Load OHLCV from SQLite for trends / dashboard."""
    path = Path(db_path)
    if not path.exists():
        return pd.DataFrame(columns=SCHEMA_COLS)

    conn = sqlite3.connect(path)
    try:
        if tickers:
            placeholders = ",".join("?" * len(tickers))
            sql = (
                f"SELECT * FROM ohlcv WHERE ticker IN ({placeholders}) "
                "ORDER BY ticker, date"
            )
            df = pd.read_sql_query(sql, conn, params=[t.upper() for t in tickers])
        else:
            df = pd.read_sql_query(
                "SELECT * FROM ohlcv ORDER BY ticker, date", conn
            )
    finally:
        conn.close()
    return df
