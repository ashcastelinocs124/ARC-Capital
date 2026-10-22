"""The Planner: turns a typed topic into a suggested watchlist the user can trim before Start.

Code checks every pick before it is shown: a ticker Yahoo can't price and a series id that isn't
`fred:ID` / `yahoo:TICKER` are dropped, so the daily build never starts from a made-up id."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from castelino.agents.consultants.models import Watchlist
from castelino.agents.themes import SERIES
from castelino.agents.trade import llm
from castelino.agents.update.background import default_close
from castelino.config import get_settings

MAX_COMPANIES, MAX_SERIES, MAX_QUERIES = 8, 6, 4

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
