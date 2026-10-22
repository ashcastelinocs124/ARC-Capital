"""The Planner: turns a typed topic into a suggested watchlist the user can trim or add to before Start.

Code checks every pick before it is shown: a ticker Yahoo can't price and a series id that isn't
`fred:ID` / `yahoo:TICKER` are dropped, so the daily build never starts from a made-up id. A company or
series the user adds by hand goes through `check_company` / `check_series` the same way."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from castelino.agents.consultants.models import Company, Watchlist
from castelino.agents.themes import SERIES
from castelino.agents.trade import llm
from castelino.agents.update.background import default_close, default_fred, load_universe
from castelino.config import get_settings

MAX_COMPANIES, MAX_SERIES, MAX_QUERIES = 8, 6, 4
MAX_HAND = (
    15  # companies or series on a watchlist edited by hand: no model cost, only Yahoo/FRED calls
)

SYSTEM = """You plan the watchlist for an ARC Research topic consultant. The consultant follows one topic
every day and keeps a view on it. Given the topic, list:

- companies: listed companies central to the topic, each with its Yahoo Finance ticker (e.g. NVIDIA, NVDA;
  Taiwan Semiconductor, TSM). At most 8. A theme, a country or a market may need few or no companies: give
  none rather than stretch.
- series: data series that track the topic, as "fred:ID" (a FRED series id) or "yahoo:TICKER" (an index,
  ETF, future or currency on Yahoo Finance). At most 6. Only ids you are sure exist.
- queries: 2 to 4 short news search queries that would find today's news on the topic.

Prefer fewer, surer picks over many guesses."""


def _prices(ticker: str, close: Callable[[str], pd.Series]) -> bool:
    try:
        return not close(ticker).dropna().empty
    except Exception:  # noqa: BLE001 - an unpriceable ticker is simply dropped
        return False


def suggest(topic: str, meter: llm.Meter, *, close=default_close) -> Watchlist:
    cfg = get_settings().consultants
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Topic: {topic}"}]
    wl = llm.structured("consultant_planner", cfg.planner_model, msgs, Watchlist, meter)
    return Watchlist(
        companies=[c for c in wl.companies if _prices(c.ticker, close)][:MAX_COMPANIES],
        series=[s for s in wl.series if SERIES.match(s)][:MAX_SERIES],
        queries=[q.strip() for q in wl.queries if q.strip()][:MAX_QUERIES],
    )


def yahoo_name(ticker: str) -> str:
    """Display name: universe.csv's, else Yahoo's short name, else the ticker itself."""
    for t, name in load_universe():
        if t == ticker:
            return name
    try:
        import yfinance as yf

        return yf.Ticker(ticker).info.get("shortName") or ticker
    except Exception:  # noqa: BLE001 - a missing name never refuses a ticker that prices
        return ticker


def check_company(ticker: str, *, close=default_close, name=yahoo_name) -> Company:
    """A hand-added company: refused (ValueError) unless Yahoo prices it."""
    t = ticker.strip().upper()
    if not _prices(t, close):
        raise ValueError(
            f"{t} has no prices on Yahoo Finance. Check the ticker (e.g. TSM, 005930.KS)."
        )
    return Company(name=name(t), ticker=t)


def check_series(spec: str, *, fred=default_fred, close=default_close) -> str:
    """A hand-added series as "fred:ID" / "yahoo:TICKER": refused (ValueError) unless it returns data."""
    m = SERIES.match(spec.strip())
    if not m:
        raise ValueError(f"{spec!r} is not fred:ID or yahoo:TICKER.")
    provider, sid = m.groups()
    sid = sid.upper() if provider == "fred" else sid
    where = "fred.stlouisfed.org" if provider == "fred" else "finance.yahoo.com"
    if not _prices(sid, fred if provider == "fred" else close):
        raise ValueError(f"{provider}:{sid} returned no data. Check the id on {where}.")
    return f"{provider}:{sid}"
