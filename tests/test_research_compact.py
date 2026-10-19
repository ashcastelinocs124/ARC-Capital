from datetime import datetime

import pytest

from castelino.agents.research.deep import compact, store
from castelino.agents.research.deep.models import (
    Clarification,
    Job,
    Point,
    Proposal,
    ResearchReport,
    Summary,
)
from castelino.agents.trade import llm
from castelino.agents.weekly.models import BoardPost
from tests.research_fakes import agent, fact
from tests.trade_fakes import FakeClient, parsed

NOW = datetime(2026, 11, 5, 12, 0)


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))


def saved(created="2026-10-19T10:00:00.000000"):
    s = store.create("AI adoption", Clarification(question="Q?", questions=[]))
    a = agent(
        "A",
        facts=[fact("A1", "9.2%", [9.2]), fact("A2", "uncited", [1.0])],
        transcript=[{"role": "user", "content": "u"}],
    )
    with store.edit(s.id) as x:
        x.created_at, x.status, x.agents = created, "complete", [a]
        x.report = ResearchReport(
            title="t",
            subtitle="s",
            points=[Point(id="p1", agent="A", headline="h", body="b", fact_ids=["A1"])],
        )
        x.board = [BoardPost(agent="A", note="n", fact_ids=["A1"])]
        x.board_facts = {"A1": a.facts[0]}
        x.proposals = [
            Proposal(
                n=1,
                point_id="p1",
                agent="A",
                text="?",
                base_version=1,
                created_at="x",
                status="rejected",
            )
        ]
    return store.load(s.id)


def test_due_after_14_days_when_complete_and_idle():
    s = saved()
    assert compact.due(s, NOW)
    assert not compact.due(s, datetime(2026, 10, 25))
    assert not compact.due(s.model_copy(update={"compacted_at": "x"}), NOW)
    running = Job(step="run", state="running", at="x")
    assert not compact.due(s.model_copy(update={"job": running}), NOW)
    assert not compact.due(s.model_copy(update={"status": "writing"}), NOW)


def test_a_failed_compaction_is_not_resubmitted_by_itself():
    s = saved()
    for state in ("failed", "interrupted"):
        failed = Job(step="compact", state=state, at="x")
        assert not compact.due(s.model_copy(update={"job": failed}), NOW)
    after_run = Job(step="run", state="failed", at="x")
    assert compact.due(s.model_copy(update={"job": after_run}), NOW)


def test_compact_keeps_the_facts_a_pending_proposal_cites(monkeypatch):
    c = FakeClient([parsed(Summary(text="A found 9.2%."))])
    monkeypatch.setattr(llm, "_client", lambda m: c)
    s = saved()
    with store.edit(s.id) as x:
        p = x.report.points[0]
        x.proposals.append(
            Proposal(
                n=2,
                point_id="p1",
                agent="A",
                text="?",
                base_version=1,
                created_at="x",
                status="pending",
                before=p,
                after=p.model_copy(update={"fact_ids": ["A2"], "version": 2}),
            )
        )
    compact.compact(s.id, llm.Meter())
    assert [f.id for f in store.load(s.id).agents[0].facts] == ["A1", "A2"]


def test_compact_keeps_a_summary_cited_facts_and_the_edit_log(monkeypatch):
    c = FakeClient([parsed(Summary(text="A found 9.2% in BTOS [A1]."))])
    monkeypatch.setattr(llm, "_client", lambda m: c)
    s = saved()
    compact.compact(s.id, llm.Meter())
    got = store.load(s.id)
    a = got.agents[0]
    assert a.transcript is None and a.summary.startswith("A found 9.2%")
    assert [f.id for f in a.facts] == ["A1"] and got.board == [] and got.board_facts == {}
    assert got.compacted_at and len(got.proposals) == 1
    assert got.report.points[0].fact_ids == ["A1"]
    assert c.calls[0][1]["model"] == "gpt-6-luna"
