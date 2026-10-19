import pytest

from castelino.agents.research.deep import clarifier, critic, lead
from castelino.agents.research.deep.models import (
    Brief,
    Clarification,
    ClarifyQuestion,
    Critique,
    Plan,
    ResearchSession,
    StepError,
)
from castelino.agents.trade import llm
from tests.research_fakes import agent
from tests.trade_fakes import FakeClient, parsed


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    return c


def session(**kw):
    base = dict(
        id="s",
        topic="AI adoption",
        question="How fast are US firms adopting AI?",
        clarifying_questions=[
            ClarifyQuestion(question="US only?", why="scope"),
            ClarifyQuestion(question="Since when?", why="window"),
        ],
        answers={"US only?": "US first, then the EU"},
        created_at="2026-10-19T10:00:00",
        updated_at="2026-10-19T10:00:00",
    )
    base.update(kw)
    return ResearchSession(**base)


def briefs(n):
    return [Brief(name=f"Angle {i}", angle=f"Q{i}?", brief="b") for i in range(n)]


def test_clarify_caps_questions_on_gpt_6_sol(fake):
    qs = [ClarifyQuestion(question=f"q{i}?", why="w") for i in range(5)]
    fake.script = [parsed(Clarification(question="Q?", questions=qs))]
    out = clarifier.clarify("AI adoption", llm.Meter())
    assert len(out.questions) == 3 and fake.calls[0][1]["model"] == "gpt-6-sol"
    assert "Topic: AI adoption" in fake.calls[0][1]["messages"][1]["content"]


def test_plan_caps_at_8_and_marks_unanswered_questions(fake):
    fake.script = [parsed(Plan(briefs=briefs(10)))]
    out = lead.plan(session(), llm.Meter())
    user = fake.calls[0][1]["messages"][1]["content"]
    assert len(out) == 8
    assert "US only? → US first, then the EU" in user and "Since when? → (unanswered)" in user


def test_plan_with_no_angles_is_a_step_error(fake):
    fake.script = [parsed(Plan(briefs=[]))]
    with pytest.raises(StepError):
        lead.plan(session(), llm.Meter())


def test_plan_gaps_caps_at_4_and_names_the_gaps(fake):
    fake.script = [parsed(Plan(briefs=briefs(6)))]
    out = lead.plan_gaps(session(agents=[agent("A")]), ["no small-firm data"], llm.Meter())
    user = fake.calls[0][1]["messages"][1]["content"]
    assert len(out) == 4 and "no small-firm data" in user and "A · Adoption rate" in user


def test_critic_reads_findings_and_caps_gaps(fake):
    fake.script = [parsed(Critique(done=False, gaps=[f"g{i}" for i in range(6)]))]
    failed = agent("B", facts=[], findings=[]).model_copy(update={"error": "boom"})
    out = critic.review(session(agents=[agent("A"), failed]), llm.Meter())
    user = fake.calls[0][1]["messages"][1]["content"]
    assert len(out.gaps) == 4 and "9.2% of firms use AI" in user and "failed (boom)" in user
