"""Risk Agent — vol, correlation, marginal VaR, max suggested size.

Deterministic compute reads `portfolio.json` directly (the only research agent
with read access to the book). LLM frames the numbers in natural language.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.config import get_settings
from castelino.data.openbb_adapter import OpenBBError, get_adapter
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import history
from castelino.memory.schemas import RiskReport, TradeExpression

log = logging.getLogger(__name__)


class RiskFeatures(BaseModel):
    instrument_id: str
    realized_vol_60d: float
    correlation_to_book: float
    marginal_var_pct_nav: float
    suggested_max_size_pct_nav: float


def _correlation_openbb(symbols: list[str], lookback_days: int = 90) -> pd.DataFrame | None:
    """Get correlation matrix via OpenBB. Returns None on failure."""
    adapter = get_adapter()
    if not adapter.available:
        return None
    try:
        corr = adapter.correlation_matrix(symbols, lookback_days)
        if corr.empty:
            return None
        return corr
    except (OpenBBError, Exception) as e:
        log.debug("OpenBB correlation failed, using pandas fallback: %s", e)
        return None


def _returns(instrument_id: str, n_days: int) -> pd.Series:
    df = history(instrument_id, lookback_days=max(n_days + 5, 90))
    closes = df["close"].astype(float).dropna()
    rets = np.log(closes / closes.shift(1)).dropna().tail(n_days)
    return rets


def compute_risk_features(expression: TradeExpression, portfolio: Portfolio) -> RiskFeatures:
    cfg = get_settings()
    window = cfg.research.risk_correlation_window
    risk_max_pct = cfg.risk.position_max_pct_nav

    rets = _returns(expression.instrument_id, n_days=window)
    vol = float(rets.std() * np.sqrt(252)) if len(rets) > 1 else 0.0

    # Correlation to current book — equal-weighted basket of open positions.
    book_corr = 0.0
    if portfolio.positions:
        # Try OpenBB correlation first
        book_symbols = [p.instrument_id for p in portfolio.positions]
        all_symbols = [expression.instrument_id] + book_symbols
        obb_corr = _correlation_openbb(all_symbols, lookback_days=window)
        if obb_corr is not None and expression.instrument_id in obb_corr.index:
            try:
                row = obb_corr.loc[expression.instrument_id]
                book_corrs = [float(row[s]) for s in book_symbols if s in row.index]
                if book_corrs:
                    book_corr = float(np.mean(book_corrs))
            except Exception:
                obb_corr = None  # fall through to pandas fallback

        # Pandas fallback
        if obb_corr is None:
            try:
                book_returns = pd.DataFrame()
                for p in portfolio.positions:
                    book_returns[p.instrument_id] = _returns(p.instrument_id, n_days=window)
                book_returns = book_returns.dropna()
                book_avg = book_returns.mean(axis=1)
                joined = pd.concat([rets.rename("c"), book_avg.rename("b")], axis=1).dropna()
                if len(joined) >= 5:
                    book_corr = float(joined["c"].corr(joined["b"]))
            except Exception:
                book_corr = 0.0

    # Marginal VaR proxy: |corr| * vol * size = additional sigma added to book.
    target = expression.target_size_pct_nav
    marginal_var = abs(book_corr) * vol * target

    # Vol-targeted size cap: keep contribution to book sigma under 0.005 (50 bps),
    # capped by constitutional 5% NAV limit.
    if vol > 0:
        max_by_vol = min(0.005 / vol, risk_max_pct)
    else:
        max_by_vol = risk_max_pct
    suggested = max(0.005, min(target, max_by_vol))

    return RiskFeatures(
        instrument_id=expression.instrument_id,
        realized_vol_60d=vol,
        correlation_to_book=book_corr,
        marginal_var_pct_nav=marginal_var,
        suggested_max_size_pct_nav=suggested,
    )


SYSTEM = """\
You are the Risk interpreter. The numbers are computed; do not change them.

When framing:
- Vol is annualized. >0.30 is high; >0.50 is extreme.
- Correlation magnitude > 0.5 with the book is an exposure-stacking warning.
- If marginal VaR (added book sigma) exceeds 1% of NAV per day, flag it.
- Echo `suggested_max_size_pct_nav` honestly; do not soften it.

Keep the interpretation to 2-3 sentences.
"""


class RiskAgent(StructuredAgent[RiskReport]):
    name = "risk"
    output_schema = RiskReport
    tier = "fast"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, expression: TradeExpression, features: RiskFeatures) -> str:
        return (
            f"Instrument: {expression.instrument_id}, requested size: "
            f"{expression.target_size_pct_nav * 100:.2f}% NAV, "
            f"direction: {expression.direction.value}.\n\n"
            f"Computed risk features:\n"
            f"- realized_vol_60d (annualized): {features.realized_vol_60d:.4f}\n"
            f"- correlation_to_book: {features.correlation_to_book:.3f}\n"
            f"- marginal_var_pct_nav: {features.marginal_var_pct_nav:.4f}\n"
            f"- suggested_max_size_pct_nav: {features.suggested_max_size_pct_nav:.4f}\n\n"
            "Produce a RiskReport. Copy the numeric fields verbatim."
        )


def run_risk(expression: TradeExpression, portfolio: Portfolio) -> RiskReport:
    features = compute_risk_features(expression, portfolio)
    return RiskAgent()(expression=expression, features=features)
