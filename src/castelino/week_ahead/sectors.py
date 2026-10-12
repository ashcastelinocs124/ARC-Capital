"""Sectors year-to-date vs valuation: SPDR sector ETF YTD return, trailing P/E, earnings growth.

Earnings growth is the median latest-quarter y/y of each sector's top-10 stocks from the Sector
Sentiment snapshot: a cap-weighted mean let one negative base swing a sector (Industrials -373%).
"""

from __future__ import annotations

import logging
import statistics
from datetime import date

from castelino.signals.sector_sentiment import SECTOR_ETFS

log = logging.getLogger(__name__)
BENCH = ("S&P 500", "SPY")


def yf_closes(symbols: list[str], start: str):
    import yfinance as yf

    return yf.download(symbols, start=start, progress=False, auto_adjust=True)["Close"]


def yf_pe(symbol: str) -> float | None:
    import yfinance as yf

    return yf.Ticker(symbol).info.get("trailingPE")


def snapshot_stocks() -> list[dict]:
    from castelino.signals.sector_sentiment import load_snapshot

    snap = load_snapshot()
    return [s.model_dump() for s in snap.stocks] if snap else []


def _median_growth(stocks: list[dict]) -> dict[str, float]:
    by: dict[str, list[float]] = {}
    for s in stocks:
        if s.get("earnings_growth") is not None:
            by.setdefault(s["sector"], []).append(s["earnings_growth"])
    return {k: round(100 * statistics.median(v), 1) for k, v in by.items()}


def build(
    today: date,
    *,
    etfs: dict = SECTOR_ETFS,
    closes=yf_closes,
    pe=yf_pe,
    stocks=snapshot_stocks,
) -> list[dict]:
    rows = [(sec, etf) for sec, (etf, _) in etfs.items()] + [BENCH]
    px = closes([etf for _, etf in rows], f"{today.year - 1}-12-15")
    if px is None or px.empty:
        raise RuntimeError("no sector prices")
    base = px[px.index < f"{today.year}-01-01"].ffill().iloc[-1]  # last close of last year
    last = px.ffill().iloc[-1]
    growth = _median_growth(stocks())
    out = []
    for sec, etf in rows:
        try:
            p = pe(etf)
        except Exception as e:  # noqa: BLE001 - a missing P/E leaves the dot off the chart
            log.warning("sector P/E %s: %s", etf, e)
            p = None
        out.append(
            {
                "sector": sec,
                "etf": etf,
                "ytd": round(100 * (float(last[etf]) / float(base[etf]) - 1), 1),
                "pe": round(float(p), 1) if p else None,
                "earnings_growth": growth.get(sec),
            }
        )
    return out
