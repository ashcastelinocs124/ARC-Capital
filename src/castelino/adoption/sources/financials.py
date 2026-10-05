"""Trailing-twelve-month capex, R&D and revenue from yfinance quarterly statements."""

from __future__ import annotations


def _ttm(df, row: str) -> float | None:
    if df is None or getattr(df, "empty", True) or row not in df.index:
        return None
    vals = df.loc[row].dropna().sort_index(ascending=False).iloc[:4]
    if len(vals) < 4:
        return None
    return float(vals.sum())


def fetch_financials(ticker: str, yf=None) -> tuple[float | None, float | None, float | None]:
    """(capex, rnd, revenue) as TTM magnitudes. yfinance reports capex as a negative number."""
    if yf is None:
        import yfinance as yf  # imported lazily so tests never touch the network
    t = yf.Ticker(ticker)
    capex = _ttm(t.quarterly_cashflow, "Capital Expenditure")
    rnd = _ttm(t.quarterly_financials, "Research And Development")
    revenue = _ttm(t.quarterly_financials, "Total Revenue")
    return (abs(capex) if capex is not None else None, rnd, revenue)
