# WALKTHROUGH — live-market-collector

Numbered, interview-friendly path through the project.  
Goal: explain **data in → store → signal out** without an opaque notebook.

---

## 1. What problem does this solve?

You need a **repeatable collector** for daily equity/ETF bars that:

- works in a live demo (real HTTP),
- needs **no API key**,
- writes a schema that a sibling lab (`equity-stats-lab`) can analyze offline,
- shows you understand **errors, storage, and a tiny feature layer**.

---

## 2. Why Stooq CSV HTTP?

- Free daily CSV: `https://stooq.com/q/d/l/?s=aapl.us&i=d`
- No keys → happy-path demos never stall on secrets.
- Response is plain CSV → easy to show `requests` + `pandas` in an interview.

**Ask yourself:** What would change if we swapped Stooq for Polygon/Yahoo? (auth, rate limits, column mapping — fetch module only.)

---

## 3. Module map (say this out loud)

| Module        | Job |
|---------------|-----|
| `fetch.py`    | HTTP GET, validate, normalize schema, backoff |
| `store.py`    | SQLite upsert + CSV append/dedupe |
| `trends.py`   | Rolling return, MA crossover flag, text dashboard |
| `schedule.py` | Run-once wrapper + APScheduler interval |
| `cli.py`      | argparse entry: `fetch` / `run-once` / `schedule` |

---

## 4. Run the happy path

```bash
source .venv/bin/activate
python -m src.cli fetch
```

Expected side effects:

1. Network GETs logged for `aapl.us`, `msft.us`, `spy.us`
2. `data/market.db` created / upserted
3. `data/exports/market_ohlcv.csv` written/appended
4. `output/dashboard.txt` + `output/trend_features.csv`

---

## 5. Inspect storage (schema check)

```bash
# CSV
head -n 5 data/exports/market_ohlcv.csv

# SQLite
sqlite3 data/market.db "PRAGMA table_info(ohlcv);"
sqlite3 data/market.db "SELECT ticker, date, close, source, collected_at FROM ohlcv ORDER BY date DESC LIMIT 6;"
```

Confirm columns:  
`ticker, date, open, high, low, close, volume, source, collected_at`.

**Interview tip:** `PRIMARY KEY (ticker, date)` + `ON CONFLICT DO UPDATE` = idempotent re-fetch.

---

## 6. Explain the trend features

In `trends.py`:

- **Rolling return:** `close.pct_change(20)` — simple lookback performance.
- **MA crossover flag:** short SMA (20) vs long SMA (50); `+1` / `-1` on the cross day, else `0`.

Open `output/dashboard.txt` and walk an interviewer through one ticker line-by-line.

*Not alpha* — educational features that prove you can join collection to analytics.

---

## 7. On-demand vs schedule

```bash
python -m src.cli run-once          # one cycle
python -m src.cli schedule --interval 600   # every 10 min (demo only; be polite)
```

`schedule.py` uses `BlockingScheduler` so a laptop demo doesn’t need cron.  
Failures in a scheduled tick are logged; the loop continues (`max_instances=1`, `coalesce=True`).

---

## 8. Error handling story

Point at `fetch.py`:

1. **Timeout** → retry with exponential backoff + jitter  
2. **Non-200** (esp. 429 / 5xx) → backoff; other codes → fail that ticker  
3. **Empty / HTML / missing columns** → `FetchError`  
4. **`fetch_many`** → one bad ticker is skipped; others still store  

Demo idea: `python -m src.cli fetch --tickers aapl.us,notarealticker.us`

---

## 9. Link to equity-stats-lab

Hand off either:

- `data/exports/market_ohlcv.csv`, or  
- `output/trend_features.csv`, or  
- a SQLite copy of `data/market.db`

Same column contract → lab focuses on stats / plots without re-implementing HTTP.

---

## 10. Screenshot checklist (portfolio)

See README — capture: terminal fetch, CSV/SQLite sample rows, dashboard, and one error-path log.

---

## 11. Extension ideas (if asked “what next?”)

- Add unit tests with `responses` / `pytest` mocking HTTP  
- Partition CSV by ticker/date  
- Metrics export (Prometheus) for ops-flavored interviews  
- Replace interval loop with Airflow/cron in a “production” talk track  

---

## 12. One-minute closing pitch

> “I built a small collector that hits a real market CSV endpoint, handles timeouts and rate limits, upserts into SQLite with a portable CSV export, and computes interview-friendly trend flags. The sibling lab consumes the same schema for deeper stats.”
