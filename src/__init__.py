"""
live-market-collector
=====================
Student portfolio package: on-demand + scheduled equity/ETF OHLCV collection
via Stooq's free CSV HTTP API, SQLite + CSV storage, and simple trend signals.

Sibling project: equity-stats-lab (offline stats / analysis on the same schema).

What an interviewer might ask
-----------------------------
- "Why modularize fetch / store / trends / schedule instead of one script?"
  Separation of concerns: each module has one job, easier to test and explain.
- "Why Stooq without an API key?"
  Demonstrates real HTTP + parsing without credential friction for demos.
"""

__version__ = "0.1.0"
