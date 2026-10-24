"""The Planner: turns a typed topic into a suggested watchlist the user can trim or add to before Start.

Code checks every pick before it is shown: a ticker Yahoo can't price and a series id that isn't
`fred:ID` / `yahoo:TICKER` are dropped, so the daily build never starts from a made-up id. A company,
series or web page the user adds by hand goes through `check_company` / `check_series` / `check_link`."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

import httpx
import pandas as pd

from castelino.agents.consultants.models import Company, Watchlist, WatchlistDraft
from castelino.agents.themes import SERIES
from castelino.agents.trade import llm
from castelino.agents.update.background import default_close, default_fred, load_universe
from castelino.config import get_settings

MAX_COMPANIES, MAX_SERIES, MAX_QUERIES = 8, 6, 4
MAX_HAND = (
    15  # companies or series on a watchlist edited by hand: no model cost, only Yahoo/FRED calls
)
MAX_LINKS = 5  # pasted pages: each is one web search per build (llm.SEARCH_USD, ~$0.02)

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
    wl = llm.structured("consultant_planner", cfg.planner_model, msgs, WatchlistDraft, meter)
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


def page_status(url: str) -> int:
    """HTTP status of a pasted page. Refuses a host that resolves to a private address: the server is
    the one fetching, so a link must not reach Fly's internal network."""
    host = urlparse(url).hostname or ""
    for *_, addr in socket.getaddrinfo(host, None):
        if not ipaddress.ip_address(addr[0]).is_global:
            raise ValueError("a private address")
    # ponytail: redirects aren't re-checked; only the status code ever comes back, never the body
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130 Safari/537.36"
    }
    return httpx.get(url, headers=headers, follow_redirects=True, timeout=15).status_code


def check_link(url: str, *, status=page_status) -> str:
    """A hand-added web page: refused (ValueError) unless it is an http(s) address that answers. A bot
    wall (401/403/429) or a timeout passes (FRED stalls on any non-browser request): the build reads the
    page through web search, not from this server."""
    u = url.strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError(f"{u!r} is not a web address. Paste the full link, starting https://.")
    u = p._replace(fragment="").geturl()
    try:
        code = status(u)
    except httpx.TimeoutException:
        return u
    except Exception as e:  # noqa: BLE001 - DNS, refused, private address: the link is unusable
        raise ValueError(f"{p.hostname} did not answer ({str(e)[:80]}). Check the link.") from e
    if code in (404, 410):
        raise ValueError(f"That page was not found ({code}). Check the link.")
    return u
