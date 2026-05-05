"""Backtesting Agent — find similar historical setups for an instrument.

v1 similarity heuristic: rolling-window features (RSI, sma-distance, vol),
distance-weighted nearest neighbors over the lookback. The LLM interprets the
cohort statistics — it doesn't compute them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.config import get_settings
from castelino.execution.pricing import history
from castelino.memory.schemas import BacktestReport, Hypothesis, TradeExpression


class BacktestStats(BaseModel):
    instrument_id: str
    similar_setups_found: int
    hit_rate: float
    avg_return_pct: float
    max_drawdown_pct: float
    sample_period_years: float


def _features_for_setup(closes: pd.Series) -> tuple[float, float, float]:
    last = float(closes.iloc[-1])
    sma_20 = float(closes.tail(20).mean())
    sma_dist = (last - sma_20) / sma_20 if sma_20 > 0 else 0.0
    log_rets = np.log(closes / closes.shift(1)).dropna()
    vol = float(log_rets.tail(20).std() * np.sqrt(252)) if len(log_rets) >= 20 else 0.0
    # Crude RSI proxy: % positive days in last 14
    delta = closes.diff().dropna().tail(14)
    rsi_proxy = float((delta > 0).sum()) / max(len(delta), 1)
    return sma_dist, vol, rsi_proxy


def compute_backtest_stats(
    expression: TradeExpression,
    lookback_years: int | None = None,
) -> BacktestStats:
    cfg = get_settings()
    years = lookback_years or cfg.research.backtest_lookback_years
    df = history(expression.instrument_id, lookback_days=years * 252)
    closes = df["close"].astype(float).dropna()
    if len(closes) < 200:
        return BacktestStats(
            instrument_id=expression.instrument_id,
            similar_setups_found=0, hit_rate=0.0, avg_return_pct=0.0,
            max_drawdown_pct=0.0, sample_period_years=len(closes) / 252.0,
        )

    horizon = max(1, expression.expected_holding_days)
    win = 20  # window size used for setup features
    today_idx = len(closes) - 1
    today_features = _features_for_setup(closes.iloc[today_idx - win + 1 : today_idx + 1])

    sims: list[tuple[int, float]] = []  # (idx, distance)
    for i in range(win, today_idx - horizon):
        f = _features_for_setup(closes.iloc[i - win + 1 : i + 1])
        d = sum((a - b) ** 2 for a, b in zip(f, today_features, strict=False))
        sims.append((i, d))
    sims.sort(key=lambda t: t[1])
    cohort = sims[:50]
    if not cohort:
        return BacktestStats(
            instrument_id=expression.instrument_id,
            similar_setups_found=0, hit_rate=0.0, avg_return_pct=0.0,
            max_drawdown_pct=0.0, sample_period_years=len(closes) / 252.0,
        )

    rets: list[float] = []
    for idx, _ in cohort:
        entry = float(closes.iloc[idx])
        exit_ = float(closes.iloc[idx + horizon])
        signed = (exit_ - entry) / entry if expression.direction.value == "long" else (entry - exit_) / entry
        rets.append(signed)
    rets_arr = np.array(rets)
    hit_rate = float((rets_arr > 0).mean())
    avg_ret = float(rets_arr.mean()) * 100
    max_dd = float(rets_arr.min()) * 100  # worst trade in cohort

    return BacktestStats(
        instrument_id=expression.instrument_id,
        similar_setups_found=len(cohort),
        hit_rate=hit_rate,
        avg_return_pct=avg_ret,
        max_drawdown_pct=max_dd,
        sample_period_years=len(closes) / 252.0,
    )


SYSTEM = """\
You interpret backtest cohort statistics for a proposed trade. The numbers are
computed; do not recompute them.

Be honest about the signal:
- A hit rate near 50% is noise.
- A small cohort (< 20) is fragile.
- Avg return must be compared to the trade's holding cost, not zero.

Keep the interpretation to 2-3 sentences.
"""


class BacktestingAgent(StructuredAgent[BacktestReport]):
    name = "backtest"
    output_schema = BacktestReport
    tier = "fast"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, expression: TradeExpression, hypothesis: Hypothesis, stats: BacktestStats) -> str:
        return (
            f"Trade: {expression.direction.value} {expression.instrument_id} "
            f"for {expression.expected_holding_days} days.\n"
            f"Parent thesis: {hypothesis.thesis}\n\n"
            f"Cohort statistics (authoritative):\n"
            f"- similar_setups_found: {stats.similar_setups_found}\n"
            f"- hit_rate: {stats.hit_rate:.2f}\n"
            f"- avg_return_pct: {stats.avg_return_pct:.2f}\n"
            f"- max_drawdown_pct: {stats.max_drawdown_pct:.2f}\n"
            f"- sample_period_years: {stats.sample_period_years:.1f}\n\n"
            "Produce a BacktestReport. Copy the numeric fields verbatim."
        )


def run_backtest(expression: TradeExpression, hypothesis: Hypothesis) -> BacktestReport:
    stats = compute_backtest_stats(expression)
    return BacktestingAgent()(expression=expression, hypothesis=hypothesis, stats=stats)
