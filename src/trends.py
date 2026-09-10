"""
trends.py — Rolling returns, MA crossover flags, text dashboard.

What an interviewer might ask
-----------------------------
- "What signal are you computing and why?"
  Simple educational features: N-day rolling return and SMA short/long
  crossover (golden/death cross style). Not alpha — interviewable metrics.
- "How would this feed equity-stats-lab?"
  Same schema CSV/SQLite; lab does richer offline stats on collected bars.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_RETURN_WINDOW = 20
DEFAULT_MA_SHORT = 20
DEFAULT_MA_LONG = 50


def add_trend_features(
    df: pd.DataFrame,
    *,
    return_window: int = DEFAULT_RETURN_WINDOW,
    ma_short: int = DEFAULT_MA_SHORT,
    ma_long: int = DEFAULT_MA_LONG,
) -> pd.DataFrame:
    """
    Per-ticker: rolling return and MA crossover flag.

    ma_crossover_flag:
      1  = short MA crossed above long MA on this bar (golden-style)
     -1  = short MA crossed below long MA (death-style)
      0  = no cross today
    """
    if df is None or df.empty:
        return df

    parts: list[pd.DataFrame] = []
    for ticker, g in df.sort_values("date").groupby("ticker", sort=False):
        g = g.copy()
        g["close"] = pd.to_numeric(g["close"], errors="coerce")
        g["rolling_return"] = g["close"].pct_change(return_window)
        g["ma_short"] = g["close"].rolling(ma_short).mean()
        g["ma_long"] = g["close"].rolling(ma_long).mean()
        above = (g["ma_short"] > g["ma_long"]).astype(bool)
        # shift(1) leaves NA on first row — treat as False without fillna downcast warning
        prev_above = above.shift(1, fill_value=False).astype(bool)
        cross_up = above & (~prev_above)
        cross_dn = (~above) & prev_above
        g["ma_crossover_flag"] = 0
        g.loc[cross_up, "ma_crossover_flag"] = 1
        g.loc[cross_dn, "ma_crossover_flag"] = -1
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    logger.info(
        "Trend features added (return_window=%d, ma=%d/%d)",
        return_window,
        ma_short,
        ma_long,
    )
    return out


def write_dashboard(
    df: pd.DataFrame,
    output_dir: str | Path,
    *,
    return_window: int = DEFAULT_RETURN_WINDOW,
    ma_short: int = DEFAULT_MA_SHORT,
    ma_long: int = DEFAULT_MA_LONG,
) -> Path:
    """
    Write a small UTF-8 text dashboard under output/.
    Shows latest close, rolling return, MA values, and last crossover.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "dashboard.txt"

    featured = add_trend_features(
        df,
        return_window=return_window,
        ma_short=ma_short,
        ma_long=ma_long,
    )

    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append("=" * 64)
    lines.append(" live-market-collector — TEXT DASHBOARD")
    lines.append(f" generated_at: {now}")
    lines.append(
        f" windows: rolling_return={return_window}d  "
        f"MA_short={ma_short}  MA_long={ma_long}"
    )
    lines.append(" sibling: equity-stats-lab (offline stats on same schema)")
    lines.append("=" * 64)

    if featured is None or featured.empty:
        lines.append("(no data — run: python -m src.cli fetch)")
    else:
        for ticker, g in featured.groupby("ticker", sort=True):
            last = g.iloc[-1]
            rr = last.get("rolling_return")
            rr_s = f"{rr * 100:.2f}%" if pd.notna(rr) else "n/a"
            ms = last.get("ma_short")
            ml = last.get("ma_long")
            ms_s = f"{ms:.2f}" if pd.notna(ms) else "n/a"
            ml_s = f"{ml:.2f}" if pd.notna(ml) else "n/a"
            flag = int(last.get("ma_crossover_flag") or 0)
            flag_s = {1: "GOLDEN cross today", -1: "DEATH cross today"}.get(
                flag, "no cross today"
            )
            # Last non-zero cross in history
            crosses = g[g["ma_crossover_flag"] != 0]
            if not crosses.empty:
                lc = crosses.iloc[-1]
                lc_flag = int(lc["ma_crossover_flag"])
                lc_name = "golden" if lc_flag == 1 else "death"
                last_cross_s = f"{lc['date']} ({lc_name})"
            else:
                last_cross_s = "none in window"

            lines.append("")
            lines.append(f"[{ticker}]  last_date={last['date']}  close={last['close']:.2f}")
            lines.append(f"  {return_window}d rolling return : {rr_s}")
            lines.append(f"  MA{ma_short} / MA{ma_long}       : {ms_s} / {ml_s}")
            lines.append(f"  crossover flag     : {flag} ({flag_s})")
            lines.append(f"  last crossover     : {last_cross_s}")

    lines.append("")
    lines.append("=" * 64)
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    logger.info("Dashboard written -> %s", path)

    # Also write a compact features CSV for equity-stats-lab handoff
    feat_path = out_dir / "trend_features.csv"
    keep = [
        c
        for c in [
            "ticker",
            "date",
            "close",
            "rolling_return",
            "ma_short",
            "ma_long",
            "ma_crossover_flag",
        ]
        if c in featured.columns
    ]
    if not featured.empty:
        featured[keep].to_csv(feat_path, index=False)
        logger.info("Trend features CSV -> %s", feat_path)

    return path
