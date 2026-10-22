"""Trade Lab's tools: the Weekly Deep Dive's ToolBox (FRED, Yahoo, BLS, Polymarket, cited web search, board)
plus `technicals` and `cot`. Every number is computed here, never by the model, and becomes a Fact."""

from __future__ import annotations

import math
from concurrent.futures import Future, ThreadPoolExecutor

import pandas as pd

from castelino.agents.update.models import Fact, SeriesRef
from castelino.agents.weekly.tools import SPECS, ToolBox, ToolError, _obj

TRADE_SPECS: dict[str, dict] = {
    **SPECS,
    "technicals": {
        "description": "Technical read of a Yahoo ticker, computed from daily closes: 14-day RSI, MACD "
        "histogram, % vs 50/200-day averages, 3-month return, position in the 52-week range (0 = low, "
        "100 = high), 21-day volatility and its percentile over 3 years, drop from the 52-week high, and "
        'with vs (another ticker, or "" for none) its relative strength.',
        "parameters": _obj({"ticker": {"type": "string"}, "vs": {"type": "string"}}),
    },
    "cot": {
        "description": "CFTC positioning: net speculative position as % of open interest, its 4-week "
        "change and where it sits in its 3-year range. Markets: S&P 500, Nasdaq 100, 10-year Treasury, "
        "Gold, WTI crude, US dollar index, Japanese yen.",
        "parameters": _obj({"market": {"type": "string"}}),
    },
}
# CFTC contract market codes. ponytail: S&P 500 and the 10-year are the codes Cross-Asset Drivers already
# uses; the others come from CFTC's public list. A wrong code only returns "no rows" as a tool error.
COT = {
    "S&P 500": "13874A",
    "10-year Treasury": "043602",
    "Nasdaq 100": "209742",
    "Gold": "088691",
    "WTI crude": "067651",
    "US dollar index": "098662",
    "Japanese yen": "097741",
}


def prefix(code: str, n: int) -> str:
    return f"{code}{n}."


def _pos(s: pd.Series) -> float:
    lo, hi = float(s.min()), float(s.max())
    return 50.0 if hi == lo else (float(s.iloc[-1]) - lo) / (hi - lo) * 100


def technical_numbers(px: pd.Series, bench: pd.Series | None) -> dict[str, float]:
    from castelino.signals.sector_sentiment import _technicals_from_closes

    px = px.dropna()
    if len(px) < 260:
        raise ToolError("need at least 260 daily closes")
    t = _technicals_from_closes([float(v) for v in px.values])
    year = px.iloc[-252:]
    vol = px.pct_change().rolling(21).std().dropna() * math.sqrt(252) * 100
    v3 = vol.iloc[-756:]

    def pct(v):
        return None if v is None else v * 100

    out = {
        "rsi14": t["rsi14"],
        "macd_hist": t["macd_hist"],
        "vs_sma50": pct(t["vs_sma50"]),
        "vs_sma200": pct(t["vs_sma200"]),
        "ret_3m": pct(t["ret_3m"]),
        "range_pos": _pos(year),
        "vol21": float(vol.iloc[-1]),
        "vol_pct": float((v3 <= v3.iloc[-1]).mean() * 100),
        "dd_52w": (float(px.iloc[-1]) / float(year.max()) - 1) * 100,
    }
    if bench is not None:
        ratio = (px / bench.reindex(px.index).ffill()).dropna()
        out["rs_3m"] = (float(ratio.iloc[-1]) / float(ratio.iloc[-64]) - 1) * 100
        out["rs_pos"] = _pos(ratio.iloc[-756:])
    return {
        k: (round(v, 2) if k == "macd_hist" else round(v, 1))
        for k, v in out.items()
        if v is not None
    }


class TradeToolBox(ToolBox):
    def __init__(self, *args, cftc=None, meter=None, **kw):
        super().__init__(*args, **kw)
        self._cftc, self.meter = cftc, meter
        self._early: dict[str, Future] = {}

    def specs(self) -> list[dict]:
        names = [*self.allowed, "post_to_board", "read_board"]
        specs = [{"type": "function", "name": n, "strict": True, **TRADE_SPECS[n]} for n in names]
        return specs + self.consult_specs()

    def prefetch(self, calls: list[tuple[str, dict | None]]) -> None:
        """Run a turn's web searches at once (each takes ~30s). call() still takes them in order, so fact ids
        and the budget come out as before; a search past the budget never starts."""
        room = max(0, self.max_calls - self.calls)
        qs = {
            a["query"]
            for n, a in calls[:room]
            if n == "web_search" and isinstance(a, dict) and isinstance(a.get("query"), str)
        }
        if "web_search" not in self.allowed or len(qs) < 2:
            return
        with ThreadPoolExecutor(len(qs)) as pool:  # ids are renumbered when call() takes each one
            self._early = {q: pool.submit(ToolBox._web_search, self, q) for q in qs}

    def _web_search(self, query: str) -> list[Fact]:
        from castelino.agents.trade.llm import SEARCH_USD

        if (
            self.meter is not None
        ):  # searches run outside llm.py, so they're priced here for the cap
            self.meter.add(SEARCH_USD)
        if early := self._early.pop(query, None):
            return self._renumber(early.result())
        return super()._web_search(query)

    def _technicals(self, ticker: str, vs: str) -> list[Fact]:
        px = self.yahoo(ticker)
        px = px[px.index <= pd.Timestamp(self.end)]
        bench = None
        if vs.strip():
            bench = self.yahoo(vs.strip())
            bench = bench[bench.index <= pd.Timestamp(self.end)]
        n = technical_numbers(px, bench)
        parts = [
            f"14-day RSI {n['rsi14']}" if "rsi14" in n else "",
            f"MACD histogram {n['macd_hist']:+.2f}" if "macd_hist" in n else "",
            f"{n['vs_sma50']:+.1f}% vs 50-day average" if "vs_sma50" in n else "",
            f"{n['vs_sma200']:+.1f}% vs 200-day average" if "vs_sma200" in n else "",
            f"3-month return {n['ret_3m']:+.1f}%" if "ret_3m" in n else "",
            f"{n['range_pos']:.1f}% of the way from its 52-week low to high",
            f"21-day volatility {n['vol21']:.1f}% (percentile {n['vol_pct']:.1f} over 3 years)",
            f"{n['dd_52w']:+.1f}% from its 52-week high",
        ]
        if bench is not None:
            parts.append(
                f"vs {vs.strip()}: {n['rs_3m']:+.1f}% over 3 months, "
                f"{n['rs_pos']:.1f}% of its 3-year range"
            )
        day = px.index[-1]
        return [
            Fact(
                id=self._ids(1)[0],
                text=f"{ticker} technicals on {day:%Y-%m-%d}: " + "; ".join(p for p in parts if p),
                numbers=list(n.values()),
                provenance="data",
                series=SeriesRef(kind="daily", provider="yahoo", id=ticker, label=ticker),
                source_title=f"Yahoo Finance {ticker} (computed by ARC)",
                source_url=f"https://finance.yahoo.com/quote/{ticker}",
            )
        ]

    def _cot(self, market: str) -> list[Fact]:
        code = COT.get(market)
        if not code:
            raise ToolError(f"no COT data for {market}; markets: {', '.join(COT)}")
        from castelino.cross_asset.factors import fetch_cftc

        s = (self._cftc or fetch_cftc)(code).dropna()
        s = s[s.index <= pd.Timestamp(self.end)]
        if len(s) < 10:
            raise ToolError(f"{market}: too few CFTC reports")
        last, chg = round(float(s.iloc[-1]), 1), round(float(s.iloc[-1] - s.iloc[-5]), 1)
        pos = round(_pos(s.iloc[-156:]), 1)
        return [
            Fact(
                id=self._ids(1)[0],
                text=f"{market} net speculative position {last}% of open interest on "
                f"{s.index[-1]:%Y-%m-%d}; {chg:+.1f} points in 4 weeks; {pos}% of its 3-year range",
                numbers=[last, chg, pos],
                provenance="data",
                source_title=f"CFTC Commitments of Traders, {market}",
                source_url="https://publicreporting.cftc.gov/",
            )
        ]


def chat_tools(box: ToolBox) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["description"],
                "parameters": s["parameters"],
                "strict": True,
            },
        }
        for s in box.specs()
    ]
