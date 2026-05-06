"""Technical Analysis Agent — deterministic compute + LLM interpretation."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.config import get_settings
from castelino.data.openbb_adapter import OpenBBError, get_adapter
from castelino.execution.pricing import PricingError, history
from castelino.memory.schemas import TAReport, TradeExpression

log = logging.getLogger(__name__)


# ────────────────────── deterministic compute ──────────────────────


class TAFeatures(BaseModel):
    instrument_id: str
    last_close: float
    sma_50: float
    sma_200: float
    rsi_14: float
    realized_vol_30d: float
    key_support: float
    key_resistance: float


def _compute_ta_openbb(instrument_id: str) -> TAFeatures | None:
    """Try to compute TA features via OpenBB. Returns None on failure."""
    adapter = get_adapter()
    if not adapter.available:
        return None
    try:
        hist = adapter.history(instrument_id, lookback_days=260)
        if hist.empty or len(hist) < 50:
            return None

        closes: pd.Series = hist["close"].astype(float).dropna()
        if len(closes) < 50:
            return None

        last = float(closes.iloc[-1])
        sma_50 = float(closes.tail(50).mean())
        sma_200 = float(closes.tail(min(200, len(closes))).mean())

        # RSI via OpenBB technical indicators
        rsi = 50.0
        try:
            indicators = adapter.technical_indicators(instrument_id, ["rsi"])
            rsi_data = indicators.get("rsi")
            if rsi_data and isinstance(rsi_data, list) and len(rsi_data) > 0:
                last_record = rsi_data[-1]
                rsi_val = next(
                    (v for k, v in last_record.items() if "rsi" in k.lower() and v is not None),
                    None,
                )
                if rsi_val is not None:
                    rsi = float(rsi_val)
        except (OpenBBError, Exception):
            # Fall back to manual RSI from closes
            delta = closes.diff().dropna()
            up = delta.clip(lower=0)
            down = -delta.clip(upper=0)
            avg_up = up.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
            avg_down = down.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
            rs = avg_up / avg_down.replace(0, np.nan)
            rsi_series = 100 - (100 / (1 + rs))
            if not np.isnan(rsi_series.iloc[-1]):
                rsi = float(rsi_series.iloc[-1])

        log_rets = np.log(closes / closes.shift(1)).dropna()
        realized_vol = float(log_rets.tail(30).std() * np.sqrt(252)) if len(log_rets) >= 30 else 0.0

        window = closes.tail(60)
        return TAFeatures(
            instrument_id=instrument_id,
            last_close=last,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi,
            realized_vol_30d=realized_vol,
            key_support=float(window.min()),
            key_resistance=float(window.max()),
        )
    except (OpenBBError, Exception) as e:
        log.debug("OpenBB TA failed for %s, using pandas fallback: %s", instrument_id, e)
        return None


def compute_ta_features(instrument_id: str, lookback_days: int | None = None) -> TAFeatures:
    # Try OpenBB first
    obb_result = _compute_ta_openbb(instrument_id)
    if obb_result is not None:
        return obb_result

    cfg = get_settings()
    n = lookback_days or cfg.research.ta_lookback_days
    df = history(instrument_id, lookback_days=max(n, 252))
    closes: pd.Series = df["close"].astype(float).dropna()
    if len(closes) < 50:
        raise PricingError(f"insufficient history for TA on {instrument_id}")

    last = float(closes.iloc[-1])
    sma_50 = float(closes.tail(50).mean())
    sma_200 = float(closes.tail(min(200, len(closes))).mean())

    # RSI(14) — classic Wilder formulation
    delta = closes.diff().dropna()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_up = up.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_down = down.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0

    log_rets = np.log(closes / closes.shift(1)).dropna()
    realized_vol = float(log_rets.tail(30).std() * np.sqrt(252)) if len(log_rets) >= 30 else 0.0

    # Support / resistance: rolling 20d low / high (simple, robust enough for v1).
    window = closes.tail(60)
    support = float(window.min())
    resistance = float(window.max())

    return TAFeatures(
        instrument_id=instrument_id,
        last_close=last,
        sma_50=sma_50,
        sma_200=sma_200,
        rsi_14=rsi,
        realized_vol_30d=realized_vol,
        key_support=support,
        key_resistance=resistance,
    )


# ────────────────────── LLM interpretation ──────────────────────


SYSTEM = """\
You are the Technical Analysis interpreter. The numbers are computed for you;
your job is to explain what they mean for the proposed trade in plain English.

Rules:
- Do NOT recompute or override the numbers. They are authoritative.
- State the trend (uptrend/downtrend/range) consistent with sma_50 vs sma_200.
- Call out RSI extremes (>70 overbought, <30 oversold) only if relevant.
- Note where price sits relative to support/resistance.
- Keep `interpretation` to 2–4 sentences.
"""


class _TARequest(BaseModel):
    features: TAFeatures
    expression: TradeExpression


class TechnicalAnalysisAgent(StructuredAgent[TAReport]):
    name = "ta"
    output_schema = TAReport
    tier = "fast"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, expression: TradeExpression, features: TAFeatures) -> str:
        return (
            f"Instrument: {expression.instrument_id} (proposed direction: {expression.direction.value})\n\n"
            f"Computed features (authoritative — do not change):\n"
            f"- last_close: {features.last_close:.4f}\n"
            f"- sma_50: {features.sma_50:.4f}\n"
            f"- sma_200: {features.sma_200:.4f}\n"
            f"- rsi_14: {features.rsi_14:.2f}\n"
            f"- realized_vol_30d (annualized): {features.realized_vol_30d:.4f}\n"
            f"- key_support: {features.key_support:.4f}\n"
            f"- key_resistance: {features.key_resistance:.4f}\n\n"
            "Produce a TAReport. Set instrument_id and copy the numeric fields verbatim."
        )


def run_ta(expression: TradeExpression) -> TAReport:
    features = compute_ta_features(expression.instrument_id)
    return TechnicalAnalysisAgent()(expression=expression, features=features)
