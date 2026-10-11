from datetime import date

import pytest

from castelino.agents.weekly.board import Board
from castelino.agents.weekly.models import (
    AnswerDraft,
    FindingDraft,
    FindingDrafts,
    GrillQuestion,
    SubAgentSpec,
)
from castelino.agents.weekly.subagent import AgentSession, slug
from castelino.agents.weekly.tools import ToolBox
from tests.weekly_fixtures import FakeOpenAI, call, resp, series

SPEC = SubAgentSpec(
    name="Rates desk",
    description="US rates",
    goal="Explain the 10y move",
    tools=["fred_series"],
    related=["AI & chips desk"],
)
DGS10 = call("fred_series", {"series_id": "DGS10", "start": "2026-07-01"})


def session(client, max_calls=12):
    box = ToolBox(
        agent="Rates desk",
        prefix="A",
        allowed=["fred_series"],
        board=Board(),
        end=date(2026, 10, 9),
        max_calls=max_calls,
        fred=lambda sid: series([4.10, 4.17, 4.38]),
    )
    return AgentSession(
        SPEC,
        box,
        client=client,
        model="m",
        start=date(2026, 10, 5),
        end=date(2026, 10, 9),
        answer_calls=4,
        cap=6,
    )


def one_finding(ids=("A1",)):
    return FindingDrafts(
        findings=[FindingDraft(claim="c", figure=None, unit="", fact_ids=list(ids))]
    )


def test_slug():
    assert slug("AI & Chips desk") == "ai-chips-desk"


def test_run_executes_tools_then_keeps_only_findings_citing_real_facts():
    drafts = FindingDrafts(
        findings=[
            FindingDraft(claim="10y up 28bp", figure=28, unit="bp", fact_ids=["A1", "Z9"]),
            FindingDraft(claim="invented", figure=None, unit="", fact_ids=["Z9"]),
        ]
    )
    client = FakeOpenAI([resp("r1", DGS10), resp("r2")], [drafts])
    run = session(client).run("brief")
    assert [(f.id, f.fact_ids) for f in run.findings] == [("rates-desk-1", ["A1"])]
    assert run.findings[0].series.id == "DGS10" and run.tool_calls == 1
    second = client.responses.create_calls[1]
    assert second["previous_response_id"] == "r1"
    out = second["input"][0]
    assert out["type"] == "function_call_output" and out["call_id"] == "c1"
    assert "read_board" in client.responses.create_calls[0]["instructions"]


def test_exhausted_budget_turns_tools_off():
    client = FakeOpenAI([resp("r1", DGS10), resp("r2")], [one_finding()])
    session(client, max_calls=1).run("brief")
    assert client.responses.create_calls[1]["tool_choice"] == "none"


def test_no_real_findings_fails_the_desk():
    client = FakeOpenAI([resp("r1")], [FindingDrafts(findings=[])])
    with pytest.raises(RuntimeError, match="no findings"):
        session(client).run("brief")


def test_answer_continues_same_conversation_with_fresh_budget():
    t10 = call("fred_series", {"series_id": "T10YIE", "start": "2026-07-01"}, cid="c2")
    client = FakeOpenAI(
        [resp("r1", DGS10), resp("r2"), resp("r3", t10), resp("r4")],
        [one_finding(), AnswerDraft(answer="Breakevens rose only 3bp.", fact_ids=["A2", "Q1"])],
    )
    s = session(client, max_calls=1)
    s.run("brief")
    q = GrillQuestion(agent="Rates desk", finding_id="rates-desk-1", question="Growth story?")
    ex = s.answer(q)
    assert ex.answer.startswith("Breakevens") and ex.fact_ids == ["A2"]
    assert client.responses.create_calls[2]["previous_response_id"] == "p1"
