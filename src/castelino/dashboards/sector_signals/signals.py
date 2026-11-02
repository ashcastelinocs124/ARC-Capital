"""The technical signal library: prices in, event dates out.

Every signal is an *event*, the first day a condition turns true, not every day it stays true, so
one oversold spell counts once. After an event the same signal can't fire again on that sector for
`cooldown` trading days, so a choppy cross that flips back and forth isn't counted five times.

`expected` is the textbook reading (+1 = should rise afterwards, -1 = should fall). The tests are
two-sided, so the data can disagree with the textbook; the dashboard says when it does.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Signal:
    id: str
    label: str
    expected: int  # +1 textbook bullish, -1 textbook bearish
    family: str  # groups the heatmap columns
    description: str
    fn: Callable[
        [pd.DataFrame, pd.Series], pd.Series
    ]  # (ohlcv, spy close) -> condition, bool per day


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (exponential smoothing with alpha = 1/period)."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(dn != 0, 100.0).where(up.notna())


def macd_hist(close: pd.Series) -> pd.Series:
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    return line - line.ewm(span=9, adjust=False).mean()


def _compare(a: pd.Series, b: pd.Series | float, gt: bool) -> pd.Series:
    """a > b (or a < b) as a nullable boolean: <NA> where either side is missing. A condition that
    was <NA> yesterday can't "turn true" today, so the end of a warm-up period never fires."""
    b_ok = b.notna() if isinstance(b, pd.Series) else True
    out = ((a > b) if gt else (a < b)).astype("boolean")
    return out.mask(~(a.notna() & b_ok))


def _above(a: pd.Series, b: pd.Series | float) -> pd.Series:
    return _compare(a, b, gt=True)


def _below(a: pd.Series, b: pd.Series | float) -> pd.Series:
    return _compare(a, b, gt=False)


def _bollinger(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    mid = close.rolling(20).mean()
    sd = close.rolling(20).std()
    return mid + 2 * sd, mid - 2 * sd


def _vol_spike(df: pd.DataFrame) -> pd.Series:
    avg = df["volume"].rolling(20).mean().shift(1)
    return _above(df["volume"], 2 * avg) & (avg > 0)


def _rs(df: pd.DataFrame, spy: pd.Series) -> tuple[pd.Series, pd.Series]:
    ratio = df["close"] / spy.reindex(df.index)
    return ratio, ratio.rolling(50).mean()


def _sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n).mean()


SIGNALS: list[Signal] = [
    Signal("rsi_oversold", "RSI < 30", +1, "Momentum",
           "14-day RSI drops below 30: textbook oversold, a bounce is expected.",
           lambda df, spy: _below(rsi(df["close"]), 30)),
    Signal("rsi_overbought", "RSI > 70", -1, "Momentum",
           "14-day RSI rises above 70: textbook overbought, a pullback is expected.",
           lambda df, spy: _above(rsi(df["close"]), 70)),
    Signal("macd_bull", "MACD bull cross", +1, "Momentum",
           "MACD line crosses above its 9-day signal line.",
           lambda df, spy: _above(macd_hist(df["close"]), 0.0)),
    Signal("macd_bear", "MACD bear cross", -1, "Momentum",
           "MACD line crosses below its 9-day signal line.",
           lambda df, spy: _below(macd_hist(df["close"]), 0.0)),
    Signal("golden_cross", "Golden cross", +1, "Trend",
           "50-day average crosses above the 200-day average.",
           lambda df, spy: _above(_sma(df["close"], 50), _sma(df["close"], 200))),
    Signal("death_cross", "Death cross", -1, "Trend",
           "50-day average crosses below the 200-day average.",
           lambda df, spy: _below(_sma(df["close"], 50), _sma(df["close"], 200))),
    Signal("above_200d", "Reclaims 200-day", +1, "Trend",
           "Price closes back above its 200-day average.",
           lambda df, spy: _above(df["close"], _sma(df["close"], 200))),
    Signal("below_200d", "Loses 200-day", -1, "Trend",
           "Price closes below its 200-day average.",
           lambda df, spy: _below(df["close"], _sma(df["close"], 200))),
    Signal("high_52w", "52-week high", +1, "Breakout",
           "Close above the highest close of the prior 252 trading days.",
           lambda df, spy: _above(df["close"], df["close"].rolling(252).max().shift(1))),
    Signal("low_52w", "52-week low", -1, "Breakout",
           "Close below the lowest close of the prior 252 trading days.",
           lambda df, spy: _below(df["close"], df["close"].rolling(252).min().shift(1))),
    Signal("bb_lower", "Below lower Bollinger", +1, "Breakout",
           "Close below the 20-day, 2-standard-deviation lower band: stretched, a snap-back is expected.",
           lambda df, spy: _below(df["close"], _bollinger(df["close"])[1])),
    Signal("bb_upper", "Above upper Bollinger", -1, "Breakout",
           "Close above the 20-day, 2-standard-deviation upper band: stretched, a fade is expected.",
           lambda df, spy: _above(df["close"], _bollinger(df["close"])[0])),
    Signal("volume_up", "Volume surge, up day", +1, "Volume",
           "Volume over twice its 20-day average on a day the sector rose.",
           lambda df, spy: _vol_spike(df) & _above(df["close"].pct_change(), 0.0)),
    Signal("volume_down", "Volume surge, down day", -1, "Volume",
           "Volume over twice its 20-day average on a day the sector fell.",
           lambda df, spy: _vol_spike(df) & _below(df["close"].pct_change(), 0.0)),
    Signal("rs_up", "Beats S&P (RS cross up)", +1, "Relative strength",
           "Sector / SPY price ratio crosses above its own 50-day average.",
           lambda df, spy: _above(*_rs(df, spy))),
    Signal("rs_down", "Lags S&P (RS cross down)", -1, "Relative strength",
           "Sector / SPY price ratio crosses below its own 50-day average.",
           lambda df, spy: _below(*_rs(df, spy))),
]  # fmt: skip

BY_ID = {s.id: s for s in SIGNALS}


def onsets(cond: pd.Series, cooldown: int) -> np.ndarray:
    """Positions where `cond` turns from False to True, at least `cooldown` days after the last one.

    The day before must be a known False: the first row, and the first day after a missing value
    (an indicator's warm-up), can't be onsets."""
    c = cond.astype("boolean")
    now = c.fillna(False).to_numpy(dtype=bool)
    was_false = (~c).fillna(False).to_numpy(dtype=bool)
    turned = np.flatnonzero(now[1:] & was_false[:-1]) + 1
    out: list[int] = []
    for i in turned:
        if not out or i - out[-1] >= cooldown:
            out.append(int(i))
    return np.asarray(out, dtype=int)


def events(df: pd.DataFrame, spy_close: pd.Series, cooldown: int) -> dict[str, np.ndarray]:
    """Signal id -> event positions (row numbers in df), for one sector."""
    return {s.id: onsets(s.fn(df, spy_close), cooldown) for s in SIGNALS}
