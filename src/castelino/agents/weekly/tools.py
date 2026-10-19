"""Tool registry for trend sub-agents. Every data tool turns its result into Facts in code,
so the numbers a desk can cite always come from data or a cited source line."""

from __future__ import annotations

import logging
import re
from datetime import date

import pandas as pd

from castelino.agents.update.charts import is_rate
from castelino.agents.update.facts import facts_from_search
from castelino.agents.update.models import Fact, Point, SeriesRef
from castelino.agents.weekly.board import Board

log = logging.getLogger(__name__)

SEARCH_SYSTEM = (
    "You are a markets research assistant. Report only what reputable sources published. "
    "Quote figures exactly. One bullet per fact, each ending with its citation."
)

_START = {"type": "string", "description": "Window start, YYYY-MM-DD (e.g. 90 or 365 days back)"}


def _obj(props: dict) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


SPECS: dict[str, dict] = {
    "fred_series": {
        "description": "A FRED series (e.g. DGS10, DGS2, T10YIE, DFII10, BAMLH0A0HYM2, ICSA) from "
        "start to the week's end: levels, change, last-week change, high and low.",
        "parameters": _obj({"series_id": {"type": "string"}, "start": _START}),
    },
    "yahoo_prices": {
        "description": "Daily closes for a Yahoo Finance ticker (e.g. ^GSPC, ^SOX, NVDA, BZ=F, "
        "DX-Y.NYB, XLE) from start to the week's end.",
        "parameters": _obj({"ticker": {"type": "string"}, "start": _START}),
    },
    "bls_series": {
        "description": "A BLS series id (e.g. CUSR0000SAH1): the last 3 monthly m/m % changes.",
        "parameters": _obj({"series_id": {"type": "string"}}),
    },
    "polymarket_odds": {
        "description": "Polymarket markets for a tag slug (e.g. economy, fed, politics, "
        "geopolitics): current odds and 1-day / 1-week moves.",
        "parameters": _obj({"tag": {"type": "string"}}),
    },
    "web_search": {
        "description": "A cited web search about the week. Each cited line becomes a fact.",
        "parameters": _obj({"query": {"type": "string"}}),
    },
    "post_to_board": {
        "description": "Share something other desks could use, with the ids of YOUR facts "
        "behind it.",
        "parameters": _obj(
            {"note": {"type": "string"}, "fact_ids": {"type": "array", "items": {"type": "string"}}}
        ),
    },
    "read_board": {
        "description": "Read what other desks posted; their facts become citable by you.",
        "parameters": _obj({}),
    },
}


class ToolError(Exception):
    pass


_QUERY = re.compile(r"\?\S*")


def _safe(msg: str) -> str:
    """Error text goes to the model and the logs: drop URL query strings (they carry API keys)."""
    return _QUERY.sub("?…", msg)


def series_fact(fid: str, s: pd.Series, *, provider: str, sid: str, title: str, url: str) -> Fact:
    s = s.dropna()
    if len(s) < 2:
        raise ToolError(f"{sid}: fewer than 2 observations in the window")
    v0, v1 = float(s.iloc[0]), float(s.iloc[-1])
    week = s[s.index >= s.index[-1] - pd.Timedelta(days=7)]
    w0 = float(week.iloc[0])
    hi, lo = float(s.max()), float(s.min())
    head = f"{sid}: {v0:,.2f} on {s.index[0]:%Y-%m-%d} → {v1:,.2f} on {s.index[-1]:%Y-%m-%d}"
    if provider == "fred" and is_rate(sid):
        chg, wk = round((v1 - v0) * 100), round((v1 - w0) * 100)
        moves = f"change {chg:+d}bp; last week {wk:+d}bp"
    else:
        chg, wk = round((v1 / v0 - 1) * 100, 1), round((v1 / w0 - 1) * 100, 1)
        moves = f"change {chg:+.1f}%; last week {wk:+.1f}%"
    return Fact(
        id=fid,
        text=f"{head}; {moves}; window high {hi:,.2f}, low {lo:,.2f}",
        numbers=[v1, v0, chg, wk, hi, lo],
        provenance="data",
        series=SeriesRef(kind="daily", provider=provider, id=sid, label=sid),
        source_title=title,
        source_url=url,
    )


class ToolBox:
    # Deep Research's ToolBox reframes the same search for any topic (agents/research/deep/tools.py)
    search_system = SEARCH_SYSTEM
    search_frame = "Week ending {end:%Y-%m-%d}. "

    def __init__(
        self,
        *,
        agent: str,
        prefix: str,
        allowed: list[str],
        board: Board,
        end: date,
        max_calls: int,
        fred=None,
        yahoo=None,
        bls=None,
        polymarket=None,
        search=None,
        search_model: str | None = None,
    ):
        self.agent, self.prefix, self.allowed = agent, prefix, list(allowed)
        self.board, self.end, self.max_calls = board, end, max_calls
        self._fred, self._yahoo, self._bls = fred, yahoo, bls
        self._polymarket, self._search, self.search_model = polymarket, search, search_model
        self.facts: list[Fact] = []
        self.calls = 0

    # ── wiring defaults (imported lazily so tests never touch the network) ──
    def fred(self, sid: str) -> pd.Series:
        from castelino.forecast.regime import _fetch_fred_series

        return (self._fred or _fetch_fred_series)(sid)

    def yahoo(self, ticker: str) -> pd.Series:
        from castelino.forecast.regime import _fetch_yf_close

        return (self._yahoo or _fetch_yf_close)(ticker)

    def specs(self) -> list[dict]:
        names = [*self.allowed, "post_to_board", "read_board"]
        return [{"type": "function", "name": n, "strict": True, **SPECS[n]} for n in names]

    def exhausted(self) -> bool:
        return self.calls >= self.max_calls

    def _ids(self, n: int) -> list[str]:
        return [f"{self.prefix}{len(self.facts) + k + 1}" for k in range(n)]

    def _renumber(self, facts: list[Fact]) -> list[Fact]:
        ids = self._ids(len(facts))
        return [f.model_copy(update={"id": i}) for f, i in zip(facts, ids, strict=True)]

    def call(self, name: str, args: dict) -> str:
        if self.exhausted():
            return "Tool budget used up. Stop calling tools and give your findings."
        self.calls += 1
        try:
            if name == "read_board":
                return self._read_board()
            if name == "post_to_board":
                return self._post(args["note"], args["fact_ids"])
            if name not in self.allowed:
                raise ToolError(f"{name} is not one of your tools")
            new = getattr(self, f"_{name}")(**args)
        except ToolError as e:
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001 — a broken source is a tool error, never a crash
            msg = _safe(str(e))
            log.warning("%s: %s failed: %s", self.agent, name, msg)
            return f"Error: {name} failed: {msg[:200]}"
        if not new:
            return "Error: no data returned"
        self.facts += new
        return "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in new)

    def _window(self, s: pd.Series, start: str) -> pd.Series:
        return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(self.end))]

    def _fred_series(self, series_id: str, start: str) -> list[Fact]:
        s = self._window(self.fred(series_id), start)
        url = f"https://fred.stlouisfed.org/series/{series_id}"
        fid = self._ids(1)[0]
        return [
            series_fact(fid, s, provider="fred", sid=series_id, title=f"FRED {series_id}", url=url)
        ]

    def _yahoo_prices(self, ticker: str, start: str) -> list[Fact]:
        s = self._window(self.yahoo(ticker), start)
        url = f"https://finance.yahoo.com/quote/{ticker}"
        title = f"Yahoo Finance {ticker}"
        return [series_fact(self._ids(1)[0], s, provider="yahoo", sid=ticker, title=title, url=url)]

    def _bls_series(self, series_id: str) -> list[Fact]:
        from castelino.agents.update import bls

        rows = ((self._bls or bls.fetch)([series_id]).get(series_id) or [])[:4]  # newest first
        if len(rows) < 4:
            raise ToolError(f"{series_id}: fewer than 4 monthly readings")
        mm = [(rows[i][0], round((rows[i][1] / rows[i + 1][1] - 1) * 100, 1)) for i in range(3)]
        text = f"BLS {series_id} m/m: " + ", ".join(f"{p} {v:+.1f}%" for p, v in mm)
        return [
            Fact(
                id=self._ids(1)[0],
                text=text,
                numbers=[v for _, v in mm],
                provenance="data",
                series=SeriesRef(
                    kind="release",
                    provider="bls",
                    id=series_id,
                    label=f"BLS {series_id} m/m %",
                    points=[Point(label=p, value=v) for p, v in reversed(mm)],
                ),
                source_title=f"BLS {series_id}",
                source_url=f"https://data.bls.gov/timeseries/{series_id}",
            )
        ]

    def _polymarket_odds(self, tag: str) -> list[Fact]:
        from castelino.agents.update.sources import polymarket

        events = (self._polymarket or polymarket.fetch_events)(tag=tag)
        return self._renumber(polymarket.facts(events))

    def _web_search(self, query: str) -> list[Fact]:
        from castelino.data import web_search

        user = self.search_frame.format(end=self.end) + query
        search = self._search or web_search.search_cited
        text, cites = search(self.search_system, user, model=self.search_model)
        return self._renumber(facts_from_search("tmp", text, cites))

    def _post(self, note: str, fact_ids: list[str]) -> str:
        own = {f.id: f for f in self.facts if f.id.startswith(self.prefix)}
        missing = [i for i in fact_ids if i not in own]
        if missing or not fact_ids:
            raise ToolError(f"post only your own fact ids; unknown: {missing or 'none given'}")
        self.board.post(self.agent, note, [own[i] for i in fact_ids])
        return "Posted."

    def _read_board(self) -> str:
        posts, facts = self.board.read(self.agent)
        if not posts:
            return "The board is empty."
        have = {f.id for f in self.facts}
        self.facts += [f for f in facts if f.id not in have]
        by = {f.id: f for f in facts}
        lines = []
        for p in posts:
            lines.append(f"{p.agent}: {p.note}")
            lines += [f"  [{i}] {by[i].text} — {by[i].source_title}" for i in p.fact_ids]
        return "\n".join(lines)
