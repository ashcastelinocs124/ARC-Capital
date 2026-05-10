"""As-of-date pricing wrapper.

Reads the bulk-pulled `historical_prices.parquet` and returns the close
on or before the requested date. Bypasses validation that assumes "now"
(e.g. staleness check) — historical prices are by definition stale.

Activated by setting the `BACKTEST_AS_OF` environment variable on the
process. The hook lives in `castelino.execution.pricing.latest()`.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

from castelino.backtest import BACKTEST_AS_OF_ENV
from castelino.config import get_settings
from castelino.data.instruments import PriceSource

log = logging.getLogger(__name__)


HISTORICAL_PRICES_FILENAME = "historical_prices.parquet"


class HistoricalPricingError(RuntimeError):
    """Raised when as-of-date pricing cannot satisfy a request."""


def historical_prices_path() -> Path:
    return get_settings().resolved_paths.cache / HISTORICAL_PRICES_FILENAME


def current_as_of() -> date | None:
    """Read `BACKTEST_AS_OF` from env. None when not in backtest mode."""
    raw = os.environ.get(BACKTEST_AS_OF_ENV, "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise HistoricalPricingError(
            f"BACKTEST_AS_OF={raw!r} is not a valid ISO date"
        ) from e


@lru_cache(maxsize=1)
def _load_history(path_str: str) -> pd.DataFrame:
    """Cached read of the historical-prices parquet.

    Cache keyed on path-string so tests pointing at temp files re-read.
    Expected schema:
      - Columns: ['instrument_id', 'date', 'close']
      - 'date' is a `pd.Timestamp` (date-only, no tz)
    """
    p = Path(path_str)
    if not p.exists():
        raise HistoricalPricingError(
            f"Historical prices archive not found: {p}. "
            f"Run `python scripts/build_historical_prices.py` first."
        )
    df = pd.read_parquet(p)
    required = {"instrument_id", "date", "close"}
    missing = required - set(df.columns)
    if missing:
        raise HistoricalPricingError(
            f"Historical prices missing columns: {missing}"
        )
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    df = df.sort_values(["instrument_id", "date"]).reset_index(drop=True)
    return df


def clear_cache() -> None:
    """Drop the in-memory parquet cache (used in tests)."""
    _load_history.cache_clear()


def latest_as_of(instrument_id: str, as_of: date) -> "HistoricalPrice":
    """Close on or before `as_of` for `instrument_id`.

    Returns a structurally-equivalent `Price` object so callers don't
    need to branch on backtest-vs-live mode.
    """
    df = _load_history(str(historical_prices_path()))
    sub = df[df["instrument_id"] == instrument_id]
    if sub.empty:
        raise HistoricalPricingError(
            f"No historical rows for instrument {instrument_id}"
        )
    cutoff = pd.Timestamp(as_of)
    rows = sub[sub["date"] <= cutoff]
    if rows.empty:
        first = sub["date"].iloc[0]
        raise HistoricalPricingError(
            f"No price for {instrument_id} on or before {as_of} "
            f"(first available row: {first.date()})"
        )
    last = rows.iloc[-1]
    px = float(last["close"])
    asof_ts = last["date"].to_pydatetime().replace(tzinfo=UTC)
    return HistoricalPrice(
        instrument_id=instrument_id,
        price=px,
        asof=asof_ts,
        source=PriceSource.YFINANCE,
    )


# ── Lightweight container kept structurally identical to execution.pricing.Price
# We can't import that class without creating a circular dependency in the
# pricing-hook path, so we define a sibling that quacks the same.
from dataclasses import dataclass


@dataclass(frozen=True)
class HistoricalPrice:
    instrument_id: str
    price: float
    asof: datetime
    source: PriceSource
