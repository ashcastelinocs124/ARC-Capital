"""Shared fakes for the Weekly Deep Dive tests."""

import json
from types import SimpleNamespace

import pandas as pd

from castelino.agents.update.models import Fact, SeriesRef

END = pd.Timestamp("2026-10-09")


def series(vals, end=END):
    idx = pd.bdate_range(end=end, periods=len(vals))
    return pd.Series(vals, index=idx, dtype=float)


def fact(fid, nums=(4.38,), text=None, chart=True):
    return Fact(
        id=fid,
        text=text or f"fact {fid}: " + ", ".join(str(n) for n in nums),
        numbers=list(nums),
        provenance="data",
        series=SeriesRef(kind="daily", provider="fred", id="DGS10", label="10y") if chart else None,
        source_title="FRED DGS10",
        source_url="https://fred.stlouisfed.org/series/DGS10",
    )


def trend(
    title="t",
    agent="a",
    paragraphs=("p",),
    fact_ids=("A1",),
    exhibits=(),
    challenges=(),
    why=(),
    under_the_surface=(),
    market_impact=(),
    watch=(),
):
    """A TrendSection; `paragraphs` fills the high-level part (what_happened)."""
    from castelino.agents.weekly.models import TrendSection

    return TrendSection(
        title=title,
        agent=agent,
        what_happened=list(paragraphs),
        why=list(why),
        under_the_surface=list(under_the_surface),
        market_impact=list(market_impact),
        watch=list(watch),
        fact_ids=list(fact_ids),
        exhibits=list(exhibits),
        challenges=list(challenges),
    )


def line(fact_id, window_days=90):
    from castelino.agents.weekly.models import ExhibitPick

    return ExhibitPick(
        kind="line", title="t", fact_ids=[fact_id], window_days=window_days, points=[], unit=""
    )


def pick(kind, fact_ids, points=(), unit="", title="t", window_days=90):
    from castelino.agents.weekly.models import BarPoint, ExhibitPick

    return ExhibitPick(
        kind=kind,
        title=title,
        fact_ids=list(fact_ids),
        window_days=window_days,
        points=[BarPoint(fact_id=f, label=lb, value=v) for f, lb, v in points],
        unit=unit,
    )


def call(name, args, cid="c1"):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args), call_id=cid)


def resp(rid, *calls):
    return SimpleNamespace(id=rid, output=list(calls), output_text="")


class FakeResponses:
    """Scripted OpenAI `client.responses`: create() and parse() pop prepared replies."""

    def __init__(self, creates, parses):
        self.creates, self.parses = list(creates), list(parses)
        self.create_calls, self.parse_calls = [], []

    def create(self, **kw):
        self.create_calls.append(kw)
        return self.creates.pop(0)

    def parse(self, **kw):
        self.parse_calls.append(kw)
        return SimpleNamespace(id=f"p{len(self.parse_calls)}", output_parsed=self.parses.pop(0))


class FakeOpenAI:
    def __init__(self, creates, parses):
        self.responses = FakeResponses(creates, parses)
