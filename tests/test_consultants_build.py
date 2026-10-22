from datetime import date, datetime

import pandas as pd

from castelino.agents.consultants import build, store, thesis
from castelino.agents.consultants.models import Company, Part, Thesis, Watchlist
from castelino.agents.research.deep import sub_agent
from castelino.agents.research.deep.models import FindingDrafts
from castelino.agents.trade import llm
from castelino.agents.update.models import Fact

DAY = date(2026, 10, 15)
EMPTY = Watchlist(companies=[], series=[], queries=["private credit defaults"])


def fact(fid: str, nums=(1.0,)) -> Fact:
    return Fact(
        id=fid,
        text=f"t {fid}",
        numbers=list(nums),
        provenance="data",
        source_title="s",
        source_url="u",
    )


def closes(ticker: str) -> pd.Series:
    idx = pd.bdate_range(end=datetime(2026, 10, 14), periods=40)
    return pd.Series([100.0 + i for i in range(40)], index=idx)


def series_fact(provider: str, sid: str, fid: str, start: datetime) -> Fact:
    return fact(fid, (4.1,))


def test_watchlist_facts_ids_and_earnings():
    c = store.create(
        "AI",
        Watchlist(
            companies=[Company(name="NVIDIA", ticker="NVDA")], series=["fred:DGS10"], queries=[]
        ),
    )
    facts, gaps = build.watchlist_facts(
        c, DAY, close=closes, series=series_fact, eps=lambda t, d: (1.2, 1.0, 20.0)
    )
    assert [f.id for f in facts] == ["K1-20261015-1", "K1-20261015-2", "K1-20261015-3"]
    assert facts[1].numbers == [1.2, 1.0, 20.0] and "NVIDIA (NVDA)" in facts[1].text
    assert gaps == []


def test_watchlist_failure_is_a_gap_not_an_error():
    c = store.create(
        "AI", Watchlist(companies=[Company(name="X", ticker="X")], series=[], queries=[])
    )

    def boom(t):
        raise ValueError("down")

    facts, gaps = build.watchlist_facts(
        c, DAY, close=boom, series=series_fact, eps=lambda t, d: None
    )
    assert facts == [] and len(gaps) == 1 and "X" in gaps[0]


def _thesis() -> Thesis:
    p = Part(text="Funding is the squeeze.", fact_ids=[])
    return Thesis(
        happening=p,
        lean=p,
        alternative=p,
        change_mind=p,
        reason="first",
        updated="2026-10-15",
        version=1,
    )


def _research(new: list[Fact], calls: list):
    def fake(ar, question, board, x_budget, meter, max_calls=None, consult=True):
        calls.append((ar, max_calls))
        return ar.model_copy(update={"facts": [*ar.facts, *new], "error": None})

    return fake


def test_build_topic_without_tickers_uses_research_only(monkeypatch):
    c = store.create("Private credit", EMPTY)
    calls: list = []
    monkeypatch.setattr(
        sub_agent, "research", _research([fact("K1-20261015-1"), fact("K1-20261015-2")], calls)
    )
    monkeypatch.setattr(thesis, "write", lambda *a, **k: _thesis())
    build.build(c.slug, DAY, llm.Meter())
    assert [f.id for f in store.read_facts(c.slug, "2026-10-15")] == [
        "K1-20261015-1",
        "K1-20261015-2",
    ]
    assert store.read_thesis(c.slug) is not None
    assert store.load(c.slug).status == "active"
    assert [h.kind for h in store.history(c.slug)] == ["start"]
    ar, max_calls = calls[0]
    assert ar.letter == "K1-20261015-" and max_calls == 8
    assert "private credit defaults" in ar.brief.brief


def test_build_failure_marks_failed_and_keeps_going(monkeypatch):
    c = store.create("Private credit", EMPTY)
    monkeypatch.setattr(sub_agent, "research", _research([], []))
    gaps = build.build(c.slug, DAY, llm.Meter())
    x = store.load(c.slug)
    assert x.status == "failed" and x.error
    assert isinstance(gaps, list)


def test_build_is_once_per_day(monkeypatch):
    c = store.create("Private credit", EMPTY)
    calls: list = []
    monkeypatch.setattr(sub_agent, "research", _research([fact("K1-20261015-1")], calls))
    monkeypatch.setattr(thesis, "write", lambda *a, **k: _thesis())
    build.build(c.slug, DAY, llm.Meter())
    build.build(c.slug, DAY, llm.Meter())
    assert len(calls) == 1


def test_failed_build_can_be_retried_the_same_day(monkeypatch):
    c = store.create("Private credit", EMPTY)
    monkeypatch.setattr(sub_agent, "research", _research([], []))
    build.build(c.slug, DAY, llm.Meter())
    monkeypatch.setattr(sub_agent, "research", _research([fact("K1-20261015-1")], []))
    monkeypatch.setattr(thesis, "write", lambda *a, **k: _thesis())
    build.build(c.slug, DAY, llm.Meter())
    assert store.load(c.slug).status == "active"


def test_research_max_calls_param(monkeypatch):
    from castelino.agents.research.deep.models import AgentRun, Brief
    from castelino.agents.research.deep.tools import XBudget
    from castelino.agents.weekly.board import Board

    seen = {}

    def fake_run(**kw):
        seen["max_calls"] = kw["box"].max_calls
        seen["consult_ok"] = getattr(kw["box"], "consult_ok", None)
        seen["system"] = kw["system"]
        return FindingDrafts(findings=[]), []

    monkeypatch.setattr(sub_agent.loop, "run", fake_run)
    ar = AgentRun(letter="A", brief=Brief(name="n", angle="a", brief="b"))
    sub_agent.research(ar, "q", Board(), XBudget(10), llm.Meter(), max_calls=3)
    assert seen["max_calls"] == 3 and "at most 3 tool calls" in seen["system"]
    sub_agent.research(ar, "q", Board(), XBudget(10), llm.Meter(), consult=False)
    assert seen["consult_ok"] is False


def test_build_research_has_no_consult_tool(monkeypatch):
    # final review: a consultant's own build must not consult itself (or another consultant)
    c = store.create("Private credit", EMPTY)
    seen = {}

    def fake(ar, question, board, x_budget, meter, max_calls=None, consult=True):
        seen["consult"] = consult
        return ar.model_copy(update={"facts": [fact("K1-20261015-1")]})

    monkeypatch.setattr(sub_agent, "research", fake)
    monkeypatch.setattr(thesis, "write", lambda *a, **k: _thesis())
    build.build(c.slug, DAY, llm.Meter())
    assert seen["consult"] is False


def test_build_reruns_when_status_building(monkeypatch):
    c = store.create("Private credit", EMPTY)
    calls: list = []
    monkeypatch.setattr(sub_agent, "research", _research([fact("K1-20261015-1")], calls))
    monkeypatch.setattr(thesis, "write", lambda *a, **k: _thesis())
    build.build(c.slug, DAY, llm.Meter())
    with store.edit(c.slug) as x:
        x.status = "building"  # Build now pressed
    build.build(c.slug, DAY, llm.Meter())
    assert len(calls) == 2
