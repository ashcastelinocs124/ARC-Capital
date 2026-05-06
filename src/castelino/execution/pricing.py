"""Unified price adapter — single chokepoint for `latest()` and history.

Routes by `Instrument.source`. Caches in-memory (LRU) and on-disk (parquet).
Bad-data defenses: NaN, stale-timestamp, and >5σ-tick raise rather than
poison upstream agents.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from castelino.config import get_settings
from castelino.data.instruments import (
    INSTRUMENTS,
    Instrument,
    PriceSource,
    get_instrument,
)
from castelino.data.openbb_adapter import OpenBBError, get_adapter

log = logging.getLogger(__name__)


class PricingError(RuntimeError):
    """Raised when price data is missing, stale, or fails sanity checks."""


@dataclass(frozen=True)
class Price:
    instrument_id: str
    price: float
    asof: datetime  # the timestamp the source reported
    source: PriceSource


# ── Bad-data thresholds ────────────────────────────────────────────────────
MAX_STALENESS = timedelta(days=4)   # markets close weekends; allow a long weekend
SIGMA_OUTLIER = 5.0                 # >5σ tick vs trailing log-returns
MIN_HISTORY_FOR_SIGMA = 30          # not enough bars → skip the check


# ───────────────────────────── public API ─────────────────────────────────


def _try_openbb(instrument_id: str) -> Price | None:
    """Attempt OpenBB for latest price. Returns None on any failure."""
    adapter = get_adapter()
    if not adapter.available:
        return None
    try:
        obb_price = adapter.latest_price(instrument_id)
        return Price(
            instrument_id=instrument_id,
            price=obb_price.price,
            asof=obb_price.asof,
            source=PriceSource.OPENBB,
        )
    except OpenBBError as e:
        log.debug("OpenBB price failed for %s: %s — falling back", instrument_id, e)
        return None


def latest(instrument_id: str) -> Price:
    """Most recent price for `instrument_id`. Tries OpenBB first, falls back to yfinance/FRED."""
    # Primary: try OpenBB
    obb_price = _try_openbb(instrument_id)
    if obb_price is not None:
        return obb_price

    # Fallback: existing yfinance/FRED path
    inst = get_instrument(instrument_id)
    df = history(instrument_id, lookback_days=10)
    if df.empty:
        raise PricingError(f"No price history for {instrument_id}")
    last_row = df.iloc[-1]
    px = float(last_row["close"])
    asof = last_row.name if isinstance(last_row.name, pd.Timestamp) else df.index[-1]
    asof_dt = asof.to_pydatetime() if hasattr(asof, "to_pydatetime") else asof

    _validate_price(inst, px, asof_dt, df)
    return Price(
        instrument_id=instrument_id,
        price=px,
        asof=asof_dt,
        source=inst.source,
    )


def latest_many(instrument_ids: list[str]) -> dict[str, Price]:
    """Fetch many at once. Raises if any fails — fail loudly, not silently."""
    out = {}
    for iid in instrument_ids:
        out[iid] = latest(iid)
    return out


def history(instrument_id: str, lookback_days: int = 252) -> pd.DataFrame:
    """OHLC + volume DataFrame indexed by date. Cached on disk per (id, lookback bucket).

    For FRED yields, returns a single-column 'close' frame (no OHLCV).
    """
    inst = get_instrument(instrument_id)
    cache_path = _cache_path(instrument_id)

    df = _read_cache(cache_path)
    if df is not None and _cache_fresh(df) and len(df) >= min(lookback_days, 60):
        return df.tail(lookback_days)

    if inst.source == PriceSource.YFINANCE:
        df = _fetch_yf(inst, lookback_days)
    elif inst.source == PriceSource.FRED:
        df = _fetch_fred(inst, lookback_days)
    else:
        raise PricingError(f"Unknown source {inst.source}")

    if df.empty:
        raise PricingError(f"Empty history returned for {instrument_id}")

    _write_cache(cache_path, df)
    return df.tail(lookback_days)


# ───────────────────────── source adapters ────────────────────────────────


@lru_cache(maxsize=128)
def _yf_ticker_cached(symbol: str, key: int) -> pd.DataFrame:
    """LRU-cached yfinance fetch. `key` busts the cache periodically (15-min slots).

    Function-scoped to make `clear_cache()` simple.
    """
    del key  # only here to bust the LRU cache; not used in the call
    t = yf.Ticker(symbol)
    df = t.history(period="2y", auto_adjust=True)
    return df


def _fetch_yf(inst: Instrument, lookback_days: int) -> pd.DataFrame:
    bucket = int(time.time() // (15 * 60))  # 15-minute LRU buckets
    raw = _yf_ticker_cached(inst.symbol, bucket)
    if raw is None or raw.empty:
        raise PricingError(f"yfinance returned empty for {inst.symbol}")
    # Normalize column casing
    raw = raw.rename(columns=str.lower)
    df = raw[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def _fetch_fred(inst: Instrument, lookback_days: int) -> pd.DataFrame:
    """Fetch a single series from FRED.

    Prefers the official JSON API (`api.stlouisfed.org/fred/series/observations`)
    with `FRED_API_KEY` for higher rate limits + proper error responses; falls
    back to the keyless CSV endpoint if no key is configured. Returns a 'close'
    column only — yields are point values, not OHLC.
    """
    key = get_settings().fred_api_key
    if key:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={inst.symbol}&api_key={key}&file_type=json"
        )
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as e:
            raise PricingError(f"FRED API fetch failed for {inst.symbol}: {e}") from e
        rows = payload.get("observations", [])
        if not rows:
            raise PricingError(f"FRED API returned no observations for {inst.symbol}")
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"]).set_index("date")[["value"]]
        df = df.rename(columns={"value": "close"})
        return df

    # Keyless CSV fallback
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={inst.symbol}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise PricingError(f"FRED fetch failed for {inst.symbol}: {e}") from e
    from io import StringIO

    df = pd.read_csv(StringIO(resp.text))
    date_col = df.columns[0]
    val_col = df.columns[1]
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna()
    df = df.rename(columns={val_col: "close"})
    return df


# ───────────────────────── disk cache ─────────────────────────────────────


def _cache_path(instrument_id: str) -> Path:
    s = get_settings()
    p = s.resolved_paths.cache / "prices"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{instrument_id}.parquet"


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("price cache unreadable at %s: %s", path, e)
        return None


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(path)
    except Exception as e:
        # Cache failures must never crash the pipeline
        log.warning("failed to write price cache at %s: %s", path, e)


def _cache_fresh(df: pd.DataFrame) -> bool:
    """Cache is fresh if its last bar is from the previous business day or later."""
    if df.empty:
        return False
    last = df.index[-1]
    if not isinstance(last, pd.Timestamp):
        last = pd.Timestamp(last)
    age = pd.Timestamp.now() - last
    return age < pd.Timedelta(days=2)


def clear_cache() -> None:
    """Drop in-memory caches. Disk cache is left intact."""
    _yf_ticker_cached.cache_clear()


# ───────────────────────── validation ─────────────────────────────────────


def _validate_price(inst: Instrument, px: float, asof: datetime, df: pd.DataFrame) -> None:
    if px is None or not np.isfinite(px):
        raise PricingError(f"NaN/inf price for {inst.instrument_id}")
    if px <= 0:
        raise PricingError(f"Non-positive price for {inst.instrument_id}: {px}")

    asof_aware = asof if asof.tzinfo else asof.replace(tzinfo=UTC)
    age = datetime.now(UTC) - asof_aware
    if age > MAX_STALENESS:
        raise PricingError(
            f"Stale price for {inst.instrument_id}: {age} old (asof={asof_aware})"
        )

    # 5σ tick check vs trailing returns
    closes = df["close"].dropna()
    if len(closes) >= MIN_HISTORY_FOR_SIGMA:
        rets = np.log(closes / closes.shift(1)).dropna()
        if len(rets) >= 2:
            mean = float(rets.iloc[:-1].mean())
            std = float(rets.iloc[:-1].std(ddof=0))
            if std > 0:
                last_ret = float(rets.iloc[-1])
                z = abs((last_ret - mean) / std)
                if z > SIGMA_OUTLIER:
                    raise PricingError(
                        f"{inst.instrument_id}: last tick is {z:.1f}σ outlier "
                        f"({last_ret:.4f} vs mean {mean:.4f})"
                    )


# ───────────────────────── batch helpers ──────────────────────────────────


def warmup_cache(instrument_ids: list[str] | None = None) -> dict[str, str]:
    """Pre-fetch history for a list of instruments. Returns a status map.

    Useful to avoid mid-pipeline price stalls.
    """
    if instrument_ids is None:
        instrument_ids = list(INSTRUMENTS.keys())
    status: dict[str, str] = {}
    for iid in instrument_ids:
        try:
            history(iid, lookback_days=252)
            status[iid] = "ok"
        except Exception as e:
            status[iid] = f"err: {e}"
    return status
