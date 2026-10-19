import pytest

from castelino.agents.research.deep import sub_agent
from castelino.agents.research.deep.models import (
    AgentRun,
    AnswerDraft,
    FindingDraft,
    FindingDrafts,
    Point,
)
from castelino.agents.research.deep.tools import XBudget
from castelino.agents.trade import llm
from castelino.agents.weekly.board import Board
from castelino.data import web_search
from tests.research_fakes import agent, brief
from tests.trade_fakes import FakeClient, parsed, said, tool_call

TRANSCRIPT = [
    {"role": "system", "content": "You are researcher A"},
    {"role": "user", "content": "Start your research."},
    {"role": "assistant", "content": '{"findings": []}'},
]


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    def search(system, user, model=None):
        line = "- The October wave puts AI use at 9.7% of firms."
        return line, [("Census", "https://census.gov", 5, 10)]

    monkeypatch.setattr(web_search, "search_cited", search)
    return c


def point():
    return Point(
        id="p1",
        agent="A",
        headline="AI use reached 9.2% of firms.",
        body="The survey puts it at 9.2%.",
        fact_ids=["A1"],
    )


def _research(letter="A"):
    return sub_agent.research(
        AgentRun(letter=letter, brief=brief()), "Q?", Board(), XBudget(100), llm.Meter()
    )


def test_research_keeps_cited_findings_and_the_transcript(fake):
    fake.script = [
        said(calls=[tool_call("web_search", {"query": "BTOS AI use"})]),
        said("done"),
        parsed(
            FindingDrafts(
                findings=[FindingDraft(claim="9.7% of firms use AI", fact_ids=["A1", "Z9"])]
            )
        ),
    ]
    run = _research()
    assert run.error is None and run.findings[0].fact_ids == ["A1"] and run.facts[0].id == "A1"
    assert run.tool_calls == 1 and run.transcript[-1]["role"] == "assistant"
    assert run.model == "deepseek/deepseek-v4.1-flash-1017"
    assert fake.calls[0][1]["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert "Your angle: What is the adoption rate?" in fake.calls[0][1]["messages"][0]["content"]


def test_a_failed_agent_comes_back_with_its_error(fake):
    fake.script = [RuntimeError("boom")] * 3  # DeepSeek twice, then gpt-6-luna
    run = _research("B")
    assert "boom" in run.error and run.findings == []


def test_findings_without_real_facts_are_an_error(fake):
    fake.script = [
        said("nothing"),
        parsed(FindingDrafts(findings=[FindingDraft(claim="x", fact_ids=["Q1"])])),
    ]
    run = _research()
    assert run.findings == [] and "no findings" in run.error


def test_answer_resumes_the_saved_thread_with_4_more_calls(fake):
    fake.script = [
        said(calls=[tool_call("web_search", {"query": "BTOS latest wave"})]),
        said("done"),
        parsed(
            AnswerDraft(
                answer="The October wave says 9.7%.",
                change=True,
                finding="9.7% of firms use AI",
                fact_ids=["A2", "Z1"],
            )
        ),
    ]
    r = sub_agent.answer(
        agent("A", transcript=TRANSCRIPT),
        point(),
        "Is 9.2% current?",
        "Q?",
        XBudget(100),
        llm.Meter(),
    )
    sent = fake.calls[0][1]["messages"]
    assert sent[:3] == TRANSCRIPT
    assert 'The analyst says: "Is 9.2% current?"' in sent[3]["content"]
    assert "up to 4 more tool calls" in sent[3]["content"]
    assert [f.id for f in r.new_facts] == ["A2"] and r.answer.fact_ids == ["A2"] and r.calls == 1
    assert r.transcript[-1]["role"] == "assistant"


def test_answer_rebriefs_a_compacted_agent_from_its_summary(fake):
    fake.script = [
        said("ok"),
        parsed(AnswerDraft(answer="It stands.", change=False, finding="", fact_ids=["A1"])),
    ]
    ar = agent("A").model_copy(
        update={"transcript": None, "summary": "Found 9.2% in the BTOS survey."}
    )
    sub_agent.answer(ar, point(), "Source?", "Q?", XBudget(100), llm.Meter())
    first = fake.calls[0][1]["messages"][0]
    assert first["role"] == "system" and "Found 9.2% in the BTOS survey." in first["content"]
    assert "[A1] AI use reached 9.2% of firms" in first["content"]
