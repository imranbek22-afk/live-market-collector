# live-market-collector

Student portfolio project for **tech / quant insight weeks**.  
Fetches live daily OHLCV from **Stooq’s free CSV HTTP API** (no API key), stores to **SQLite + CSV**, and writes a small **text dashboard** with rolling returns and MA crossover flags.

**Sibling project:** [`equity-stats-lab`](../equity-stats-lab) — offline stats / analysis on the same schema  
(`ticker, date, open, high, low, close, volume, source, collected_at`).

Interview-explainable: modular `src/` package, real `requests` calls visible in code, heavy comments + `WALKTHROUGH.md`.

---

## Quick start (no secrets)

```bash
cd live-market-collector
python3.11 -m venv .venv          # or python3
source .venv/bin/activate
pip install -r requirements.txt

# One-shot fetch → SQLite + CSV + dashboard
python -m src.cli fetch

# Same pipeline (scheduler-compatible alias)
python -m src.cli run-once

# Interval schedule (Ctrl+C to stop)
python -m src.cli schedule --interval 3600
```

Optional config: copy `.env.example` → `.env` (defaults work without it).

Default tickers: `aapl.us`, `msft.us`, `spy.us`.

---

## Schema

| Column         | Notes                          |
|----------------|--------------------------------|
| `ticker`       | e.g. `AAPL`                    |
| `date`         | `YYYY-MM-DD` (trading day)     |
| `open/high/low/close` | floats                  |
| `volume`       | float                          |
| `source`       | `stooq`                        |
| `collected_at` | UTC ISO-ish timestamp          |

Primary store: `data/market.db` (`ohlcv` table, `PRIMARY KEY (ticker, date)`).  
CSV export/append: `data/exports/market_ohlcv.csv`.  
Tiny sample committed: `data/exports/sample_aapl.csv`.

---

## Repo layout

```
live-market-collector/
├── README.md
├── WALKTHROUGH.md          # numbered interview-friendly steps
├── requirements.txt
├── .env.example
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── __main__.py
│   ├── fetch.py            # Stooq HTTP + retries / backoff
│   ├── store.py            # SQLite upsert + CSV export
│   ├── schedule.py         # APScheduler / run-once job wrapper
│   ├── trends.py           # rolling return + MA crossover + dashboard
│   └── cli.py              # python -m src.cli …
├── data/
│   └── exports/
│       └── sample_aapl.csv
├── output/                 # dashboard.txt, trend_features.csv (generated)
└── notebooks/
    └── 01_explore_one_fetch.ipynb
```

---

## Screenshot checklist (for portfolio / interviews)

Use these when capturing terminal / file screenshots:

1. **Terminal fetch** — `python -m src.cli fetch` showing GET logs and “job ok”.
2. **Sample CSV rows** — head of `data/exports/market_ohlcv.csv` or `sample_aapl.csv`.
3. **SQLite rows** — e.g. `sqlite3 data/market.db "SELECT * FROM ohlcv LIMIT 5;"`.
4. **Dashboard** — `output/dashboard.txt` with rolling return + MA crossover.
5. **Error handling** — demo timeout / bad ticker (e.g. `--tickers notreal.us`) showing skip + log, or temporarily lower timeout.

---

## Stooq API (no key)

```
https://stooq.com/q/d/l/?s=aapl.us&i=d
```

Implemented with `requests.get` + `pandas.read_csv` in `src/fetch.py` (timeouts, non-200, empty/HTML, 429/5xx exponential backoff).

---

## Requirements

- Python **3.11+**
- See `requirements.txt` (pinned: `requests`, `pandas`, `APScheduler`, `python-dotenv`)

---

## License / intent

Educational portfolio demo. Stooq ToS / fair use apply — keep intervals polite (≥ a few minutes) for schedules.


---

## Offline / mock mode (optional)

The default path hits live Stooq over HTTPS. If Stooq is blocked on your network
(TLS errors or empty responses), you can still demo the same HTTP client against
a local Stooq-shaped mock:

```bash
# Terminal A — local CSV server (uses data/mock_stooq/)
python scripts/local_stooq_server.py --port 8765

# Terminal B — Windows PowerShell
$env:STOOQ_URL_TEMPLATE='http://127.0.0.1:8765/q/d/l/?s={symbol}&i=d'
python -m src.cli fetch
```

On a normal home/uni network, leave `STOOQ_URL_TEMPLATE` unset and call Stooq directly.
