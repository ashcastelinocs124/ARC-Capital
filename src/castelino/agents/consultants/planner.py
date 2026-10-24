"""The Planner: turns a typed topic into a suggested watchlist the user can trim or add to before Start.

Code checks every pick before it is shown: a ticker Yahoo can't price and a series id that isn't
`fred:ID` / `yahoo:TICKER` are dropped, so the daily build never starts from a made-up id. Data pages
specific to the topic come from one cited web search (`find_links`): only pages it cites are proposed, so
no link is made up, and quote or general macro sites (`_COVERED`) are dropped. A company,
series or web page the user adds by hand goes through `check_company` / `check_series` / `check_link`."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlparse

import httpx
import pandas as pd

from castelino.agents.consultants.models import Company, Watchlist, WatchlistDraft
from castelino.agents.themes import SERIES
from castelino.agents.trade import llm
from castelino.agents.update.background import default_close, default_fred, load_universe
from castelino.agents.update.facts import facts_from_search
from castelino.config import get_settings
from castelino.data import web_search

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

Look past the obvious headline series: a sector or thematic ETF, a commodity future or a FRED series that
moves with the topic beats a broad index. Prefer fewer, surer picks over many guesses."""

LINKS = """You find live data sources for an analyst who will follow a topic every day. Prices, yields,
indexes, currencies and FRED's economic series are already covered, so look for the numbers only this
topic has: ask who tracks it most closely (the industry body, regulator, exchange, specialist tracker,
survey, research group or company that publishes them) and find the pages those specialists read. List
up to 6 web pages whose page itself shows numbers on the topic (a table, chart, dashboard, odds or
rankings) that change on a set schedule. Mix kinds of source; at most 2 pages from one site. Never a
price quote or chart for a stock, ETF, index, currency, future or bond yield, and never a general site
that covers every market or country when a page specific to the topic exists. Never an article, blog
post, press release, PDF, FAQ, outlook narrative or one-off report, even if it is about the data. One page
per line: what numbers it shows and how often they update (live, daily, weekly, monthly or quarterly),
citing that page itself."""

# Hosts whose numbers are already reachable as fred:/yahoo: series, or general quote and macro sites
# that show the same prices and releases for any topic.
# ponytail: hand-kept list; add a host here when it keeps showing up in suggestions
_COVERED = (
    "fred.stlouisfed.org",
    "finance.yahoo.com",
    "tradingeconomics.com",
    "tradingview.com",
    "investing.com",
    "marketwatch.com",
    "macrotrends.net",
    "stockanalysis.com",
    "cnbc.com",
    "google.com",
)
PER_SITE = 2


def _prices(ticker: str, close: Callable[[str], pd.Series]) -> bool:
    try:
        return not close(ticker).dropna().empty
    except Exception:  # noqa: BLE001 - an unpriceable ticker is simply dropped
        return False


def _clean(url: str) -> str:
    """Drop the utm_* tags the search adds to cited links, and any #fragment."""
    p = urlparse(url)
    q = urlencode([(k, v) for k, v in parse_qsl(p.query) if not k.startswith("utm_")])
    return p._replace(query=q, fragment="").geturl()


def find_links(topic: str, meter: llm.Meter) -> list[str]:
    """Data pages on the topic that the search cites (so none is made up), at most MAX_LINKS. A failed
    search proposes none and never fails the plan."""
    meter.add(llm.SEARCH_USD)
    try:
        model = get_settings().consultants.links_model
        text, cites = web_search.search_cited(LINKS, f"Topic: {topic}", model=model)
    except Exception:  # noqa: BLE001 - the watchlist still comes back, without pages
        return []
    out: list[str] = []
    for line in facts_from_search("L", text, cites):  # one per cited line, with the page it cites
        u = _clean(line.source_url)
        p = urlparse(u)
        host = _host(u)
        if (
            p.scheme in ("http", "https")
            and not any(host == c or host.endswith("." + c) for c in _COVERED)
            and not p.path.lower().endswith(".pdf")  # a document, not a page that updates
            and u not in out
            and sum(_host(x) == host for x in out) < PER_SITE
        ):
            out.append(u)
    return out[:MAX_LINKS]


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def suggest(topic: str, meter: llm.Meter, *, close=default_close) -> Watchlist:
    cfg = get_settings().consultants
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Topic: {topic}"}]
    with ThreadPoolExecutor(1) as pool:  # the page search runs beside the Planner call
        pages = pool.submit(find_links, topic, meter)
        wl = llm.structured("consultant_planner", cfg.planner_model, msgs, WatchlistDraft, meter)
        links = pages.result()
    return Watchlist(
        companies=[c for c in wl.companies if _prices(c.ticker, close)][:MAX_COMPANIES],
        series=[s for s in wl.series if SERIES.match(s)][:MAX_SERIES],
        queries=[q.strip() for q in wl.queries if q.strip()][:MAX_QUERIES],
        links=links,
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
