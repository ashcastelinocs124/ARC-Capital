"""One-time bulk pull of historical prices for the backtest universe.

Reads `backtest.universe` + `backtest.bench_instruments` from config.yaml,
fetches daily OHLCV from yfinance for the full backtest window (with a
month of pre-roll for moving-average warm-up), and writes to
`data/cache/historical_prices.parquet`.

Schema:
    instrument_id : str
    date          : pd.Timestamp (date-only, no tz)
    close         : float
    open, high, low, volume : float (best-effort; FRED rows may be NaN)

Usage:
    python scripts/build_historical_prices.py
    python scripts/build_historical_prices.py --start 2023-09-01 --end 2026-05-08
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# Make the script runnable without `pip install -e .`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from castelino.backtest.pricing import historical_prices_path  # noqa: E402
from castelino.config import get_settings  # noqa: E402
from castelino.data.instruments import INSTRUMENTS  # noqa: E402

log = logging.getLogger("build_historical_prices")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def _yf_pull(symbol: str, start: date, end: date) -> pd.DataFrame:
    df = yf.Ticker(symbol).history(
        start=start.isoformat(), end=end.isoformat(), auto_adjust=True,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df.reset_index().rename(columns={"index": "date", "Date": "date"})
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    return df[["date"] + cols]


def build(start: date, end: date) -> Path:
    cfg = get_settings()
    universe = list(dict.fromkeys(
        cfg.backtest.universe + cfg.backtest.bench_instruments
    ))
    if not universe:
        raise SystemExit("backtest.universe + bench_instruments is empty")

    # One month of pre-roll for indicator warm-up
    pull_start = start - timedelta(days=35)

    rows: list[pd.DataFrame] = []
    for iid in universe:
        inst = INSTRUMENTS.get(iid)
        if inst is None:
            log.warning("unknown instrument %s in universe — skipping", iid)
            continue
        log.info("pulling %s (yf=%s) [%s → %s]", iid, inst.symbol, pull_start, end)
        df = _yf_pull(inst.symbol, pull_start, end)
        if df.empty:
            log.warning("yfinance returned empty for %s (yf=%s) — skipping", iid, inst.symbol)
            continue
        df["instrument_id"] = iid
        rows.append(df)

    if not rows:
        raise SystemExit("no instruments returned data — check symbols / network")

    out = pd.concat(rows, ignore_index=True)
    out = out[["instrument_id", "date", "open", "high", "low", "close", "volume"]]
    out = out.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    path = historical_prices_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path)
    log.info(
        "wrote %d rows across %d instruments to %s",
        len(out), out["instrument_id"].nunique(), path,
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2023-10-01")
    parser.add_argument("--end", default=date.today().isoformat())
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    build(start, end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
