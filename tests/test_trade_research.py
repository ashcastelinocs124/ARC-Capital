import numpy as np
import pandas as pd
import pytest

from castelino.agents.trade import desks, llm, orchestrator
from castelino.agents.trade.models import (
    Brief,
    Briefs,
    DeskFinding,
    DeskReport,
    Frame,
    ResearchItem,
    StandIn,
    StepError,
    TradeIdea,
)
from tests.trade_fakes import FakeClient, fact, parsed, said, tool_call

PX = pd.Series(np.linspace(100, 120, 400), index=pd.bdate_range("2025-06-01", periods=400))


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    return c


def idea(**kw):
    fr = Frame(
        title="India",
        thesis="t",
        stand_ins=[StandIn(ticker="INDA", role="subject", label="India")],
        horizon_months=12,
        prove_wrong=["x"],
        why_now_query="q",
    )
    base = dict(
        id="i1",
        idea="India",
        created_at="t",
        updated_at="t",
        frame=fr,
        research=[
            ResearchItem(id="r1", kind="claim", text="RBI defends 95", round=1),
            ResearchItem(id="r2", kind="question", text="Does selling slow?", round=1),
            ResearchItem(id="r3", kind="moderator", text="removed one", round=1, removed=True),
        ],
    )
    return TradeIdea(**{**base, **kw})


def briefs(item_ids=("r1", "r2"), desks_=("news_1", "news_2", "technical")):
    return Briefs(
        briefs=[
            Brief(
                desk=d,
                title=d,
                brief="b",
                must_answer=["q"],
                item_ids=list(item_ids) if d == "news_1" else [],
                tickers=["INDA"] if d == "technical" else [],
            )
            for d in desks_
        ]
    )


def test_plan_retries_when_an_item_is_not_covered(fake):
    fake.script = [parsed(briefs(item_ids=("r1",))), parsed(briefs())]
    out = orchestrator.plan(idea(), llm.Meter(), prices=lambda t: PX)
    assert [b.desk for b in out] == ["news_1", "news_2", "technical"]
    assert "r2" in fake.calls[1][1]["messages"][-1]["content"]
    assert fake.calls[0][1]["model"] == "gpt-6-sol"


def test_plan_fails_after_two_bad_desk_sets(fake):
    fake.script = [parsed(briefs(desks_=("news_1", "technical")))] * 2
    with pytest.raises(StepError, match="news_2"):
        orchestrator.plan(idea(), llm.Meter(), prices=lambda t: PX)


def fake_search(system, user, model=None):
    lines = ["Line one from reuters.", "Line two from mint."]
    text = "\n".join(lines)
    return text, [
        ("Reuters", "https://www.reuters.com/a", 2, 5),
        ("Mint", "https://livemint.com/b", len(lines[0]) + 3, len(text)),
    ]


def test_news_desk_with_few_outlets_searches_again_and_keeps_only_checked_findings(fake):
    good = DeskFinding(claim="Selling slowed in October.", fact_ids=["NA1.1"])
    unsourced = DeskFinding(claim="Selling fell 40.0%.", fact_ids=["NA1.1"])
    fake.script = [
        said(calls=[tool_call("web_search", {"query": "FPI flows"})]),
        said("done"),
        parsed(DeskReport(findings=[good, unsourced], summary="s1", unanswered=[])),
        said("done"),
        parsed(DeskReport(findings=[], summary="s2", unanswered=["u"])),
    ]
    b = briefs().briefs[0]
    runs, facts = desks.run(idea(), [b], llm.Meter(), search=fake_search)
    assert runs[0].domains == ["livemint.com", "reuters.com"]
    assert [f.claim for f in runs[0].report.findings] == ["Selling slowed in October."]
    assert runs[0].report.summary == "s2" and [f.id for f in facts] == ["NA1.1", "NA1.2"]


def test_a_talk_question_runs_one_desk_of_four_searches_with_q_facts(fake):
    """Talk 2 researches inline: one news desk, at most 4 searches, facts numbered Q<n>. so a second
    question can't reuse the first one's ids, and no top-up searches for few outlets (2026-10-16)."""
    ran: list[str] = []

    def search(system, user, model=None):
        ran.append(user)
        return fake_search(system, user, model)

    i = idea()
    i.facts.append(fact("Q1.1", "From an earlier question.", []))
    queries = [f"RBI rates {k}" for k in range(6)]
    fake.script = [
        said(calls=[tool_call("web_search", {"query": q}, f"c{k}") for k, q in enumerate(queries)]),
        said("done"),
        parsed(DeskReport(findings=[], summary="s", unanswered=[])),
    ]
    run, facts = desks.ask(i, "What did the RBI say this week?", llm.Meter(), search=search)
    assert run.desk == "talk" and len(ran) == 4
    assert facts and all(f.id.startswith("Q2.") for f in facts)
    assert len(fake.calls) == 3  # one tool loop: no outlet top-up


def test_all_desks_failing_is_a_step_error(fake):
    fake.script = [RuntimeError("down")] * 3
    with pytest.raises(StepError, match="All desks failed"):
        desks.run(idea(), [briefs().briefs[2]], llm.Meter(), yahoo=lambda t: PX)
