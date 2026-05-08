"""Technical readiness multiplier — deterministic, no LLM.

Measures how primed the market is for a headline's direction using RSI(14),
MACD histogram, and OBV trend on representative instruments. Applied between
pass 1 (LLM scoring) and pass 2 (Polymarket/X enrichment).

A headline about growth weakness when SPY is overbought with distribution
underway gets a boost. The same headline when SPY is mid-range gets no
adjustment. The same headline when SPY is oversold with accumulation gets
a penalty — the market is leaning the other way.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np
import yfinance as yf

from castelino.triggers.significance import HeadlineScore

log = logging.getLogger(__name__)

ASSET_CLASS_TO_TICKER: dict[str, str] = {
    "equity": "SPY",
    "bond_etf": "TLT",
    "fx": "UUP",
    "commodity_etf": "GLD",
    "futures": "USO",
}


@lru_cache(maxsize=32)
def _fetch_technicals(ticker: str) -> dict | None:
    """Fetch RSI(14), MACD histogram, and OBV 5-session slope for a ticker."""
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df is None or len(df) < 30:
            return None

        close = df["Close"].squeeze()
        volume = df["Volume"].squeeze()

        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1])

        # MACD histogram (12, 26, 9)
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        histogram = macd_line - signal_line
        current_hist = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2])

        # OBV 5-session slope
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        obv_slope = float(obv.iloc[-1] - obv.iloc[-5]) if len(obv) >= 5 else 0.0

        return {
            "rsi": current_rsi,
            "macd_hist": current_hist,
            "macd_hist_prev": prev_hist,
            "obv_slope": obv_slope,
        }
    except Exception as e:
        log.warning("technicals fetch failed for %s: %s", ticker, e)
        return None


def _headline_direction(score: HeadlineScore) -> str | None:
    """Determine the dominant direction of a headline for readiness alignment."""
    gd = score.growth_direction
    inf = score.inflation_direction

    if gd == "down" or inf == "down":
        return "bearish"
    if gd == "up" or inf == "up":
        return "bullish"
    return None


def _compute_multiplier(technicals: dict, direction: str) -> float:
    """Compute readiness multiplier from RSI + MACD + OBV alignment."""
    adj = 0.0
    is_bullish = direction == "bullish"
    is_bearish = direction == "bearish"

    # RSI
    rsi = technicals["rsi"]
    if rsi > 70:
        adj += 0.20 if is_bearish else -0.10
    elif rsi < 30:
        adj += 0.20 if is_bullish else -0.10

    # MACD histogram — crossing direction
    hist = technicals["macd_hist"]
    prev = technicals["macd_hist_prev"]
    if hist < 0 and prev >= 0:
        adj += 0.10 if is_bearish else -0.10
    elif hist > 0 and prev <= 0:
        adj += 0.10 if is_bullish else -0.10

    # OBV slope
    obv_slope = technicals["obv_slope"]
    if obv_slope < 0:
        adj += 0.10 if is_bearish else -0.10
    elif obv_slope > 0:
        adj += 0.10 if is_bullish else -0.10

    return max(0.7, min(1.5, 1.0 + adj))


def apply_readiness(scores: list[HeadlineScore]) -> list[HeadlineScore]:
    """Apply technical readiness multiplier to a list of headline scores."""
    if not scores:
        return scores

    adjusted: list[HeadlineScore] = []
    for s in scores:
        direction = _headline_direction(s)
        if direction is None or not s.asset_classes_affected:
            adjusted.append(s)
            continue

        multipliers: list[float] = []
        for ac in s.asset_classes_affected:
            ticker = ASSET_CLASS_TO_TICKER.get(ac)
            if not ticker:
                continue
            tech = _fetch_technicals(ticker)
            if tech is None:
                continue
            multipliers.append(_compute_multiplier(tech, direction))

        if not multipliers:
            adjusted.append(s)
            continue

        avg_mult = sum(multipliers) / len(multipliers)
        new_materiality = max(0.0, min(1.0, s.materiality * avg_mult))

        if abs(new_materiality - s.materiality) > 0.01:
            log.info(
                "readiness: %s %.2f → %.2f (×%.2f, dir=%s)",
                s.title[:50], s.materiality, new_materiality, avg_mult, direction,
            )

        adjusted.append(s.model_copy(update={"materiality": round(new_materiality, 3)}))

    return adjusted
