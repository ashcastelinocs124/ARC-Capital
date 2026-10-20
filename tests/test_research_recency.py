"""Every step that picks or judges data knows today's date and asks for the newest release."""

from datetime import date

from castelino.agents.research.deep import critic, lead, sub_agent, synthesizer, tools
from castelino.agents.research.deep.models import AgentRun, Clarification, Critique, Plan
from castelino.agents.research.deep.store import create
from castelino.agents.trade import llm
from tests.research_fakes import brief
from tests.trade_fakes import FakeClient, parsed

TODAY = f"Today is {date.today()}"


def session(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))
    return create(
        "AI adoption", Clarification(question="How fast are firms adopting AI?", questions=[])
    )


def test_search_asks_for_the_latest_release_and_a_date_on_every_fact():
    s = tools.SEARCH_SYSTEM
    assert "latest release" in s and "last 12 months" in s and "date" in s


def test_agents_look_for_the_latest_release_first():
    text = sub_agent._system(AgentRun(letter="A", brief=brief()), "Q?")
    assert (
        TODAY in text
        and "latest release" in text
        and f"before {date.today().year if date.today().month > 3 else date.today().year - 1}"
        in text
    )


def test_the_lead_and_critic_know_today(tmp_path, monkeypatch):
    s = session(tmp_path, monkeypatch)
    c = FakeClient([parsed(Plan(briefs=[brief()])), parsed(Critique(done=True, gaps=[]))])
    monkeypatch.setattr(llm, "_client", lambda m: c)
    lead.plan(s, llm.Meter())
    critic.review(s, llm.Meter())
    plan_msgs, crit_msgs = c.calls[0][1]["messages"], c.calls[1][1]["messages"]
    assert TODAY in plan_msgs[1]["content"] and "most recent" in plan_msgs[0]["content"]
    assert TODAY in crit_msgs[1]["content"] and "newest data" in crit_msgs[0]["content"]


def test_the_writer_knows_today_and_prefers_the_newest_figure(tmp_path, monkeypatch):
    s = session(tmp_path, monkeypatch)
    assert synthesizer.brief(s).startswith(TODAY)
    for system in (synthesizer.SYSTEM, synthesizer.MORE):
        assert "most recent" in system and "latest available" in system
