import pytest

from castelino.agents.research.deep import editor_desk, store, sub_agent
from castelino.agents.research.deep.models import (
    AnswerDraft,
    Busy,
    Clarification,
    Finding,
    Point,
    ResearchReport,
    RevisedPoint,
)
from castelino.agents.research.deep.sub_agent import Rethink
from castelino.agents.trade import llm
from tests.research_fakes import agent, fact
from tests.trade_fakes import FakeClient, parsed

TRANSCRIPT = [
    {"role": "system", "content": "s"},
    {"role": "user", "content": "u"},
    {"role": "assistant", "content": "{}"},
]


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    return c


def saved():
    s = store.create(
        "AI adoption", Clarification(question="How fast are US firms adopting AI?", questions=[])
    )
    b = agent(
        "B",
        facts=[fact("B1", "Large firms: 27% use AI", [27.0])],
        findings=[Finding(id="B-f1", claim="27%", fact_ids=["B1"])],
    )
    points = [
        Point(
            id="p1",
            agent="A",
            headline="AI use reached 9.2% of firms.",
            body="The survey puts it at 9.2%.",
            fact_ids=["A1"],
        ),
        Point(
            id="p2",
            agent="B",
            headline="Large firms lead at 27%.",
            body="27% of large firms use AI.",
            fact_ids=["B1"],
        ),
        Point(
            id="p3",
            agent="A",
            headline="Adoption keeps rising.",
            body="More firms plan to start.",
            fact_ids=["A1"],
        ),
    ]
    with store.edit(s.id) as x:
        x.agents = [agent("A", transcript=list(TRANSCRIPT)), b]
        x.report = ResearchReport(title="AI adoption", subtitle="US", points=points)
        x.status = "complete"
    return s.id


def rethink_to(monkeypatch, *, change=True):
    new = [fact("A2", "October wave: 9.7% of firms use AI", [9.7])]
    ans = AnswerDraft(
        answer="The October wave says 9.7%." if change else "It stands.",
        change=change,
        finding="9.7% of firms use AI" if change else "",
        fact_ids=["A2"] if change else ["A1"],
    )
    r = Rethink(
        answer=ans,
        new_facts=new if change else [],
        transcript=[*TRANSCRIPT, {"role": "user", "content": "q"}],
        calls=2,
        x_posts=0,
    )
    monkeypatch.setattr(sub_agent, "answer", lambda *a, **k: r)


def good_rewrite():
    return parsed(
        RevisedPoint(
            headline="AI use reached 9.7% of firms.",
            body="The October survey wave puts it at 9.7%.",
            fact_ids=["A2"],
        )
    )


def asked_and_rethought(monkeypatch, fake):
    sid = saved()
    editor_desk.start(sid, "p1", "Is 9.2% current?")
    rethink_to(monkeypatch)
    fake.script = [good_rewrite()]
    editor_desk.rethink(sid, 1, llm.Meter())
    return sid


def test_start_opens_one_question_per_point():
    sid = saved()
    p = editor_desk.start(sid, "p1", " Is 9.2% current? ")
    assert (p.n, p.status, p.text, p.base_version) == (1, "running", "Is 9.2% current?", 1)
    with pytest.raises(Busy):
        editor_desk.start(sid, "p1", "again")
    assert editor_desk.start(sid, "p2", "other point").n == 2
    with pytest.raises(KeyError):
        editor_desk.start(sid, "p9", "?")


def test_one_rethink_at_a_time_per_owning_agent():
    # p1 and p3 are both agent A's: two rethinks at once would mint the same new fact id
    sid = saved()
    editor_desk.start(sid, "p1", "Is 9.2% current?")
    with pytest.raises(Busy, match="A"):
        editor_desk.start(sid, "p3", "And this one?")
    assert editor_desk.start(sid, "p2", "Agent B is free").n == 2


def test_a_change_becomes_a_pending_one_point_proposal(monkeypatch, fake):
    sid = asked_and_rethought(monkeypatch, fake)
    s = store.load(sid)
    p = s.proposal(1)
    assert p.status == "pending" and p.after.version == 2 and p.after.fact_ids == ["A2"]
    assert p.after.body == "The October survey wave puts it at 9.7%."
    assert "A2" in {f.id for f in s.agent("A").facts}
    assert s.agent("A").transcript[-1]["content"] == "q"
    assert fake.calls[0][1]["model"] == "anthropic/claude-haiku-5.5"


def test_a_defended_point_is_answered_without_a_rewrite(monkeypatch, fake):
    sid = saved()
    editor_desk.start(sid, "p1", "Source?")
    rethink_to(monkeypatch, change=False)
    editor_desk.rethink(sid, 1, llm.Meter())  # fake.script is empty: a rewrite call would fail
    assert store.load(sid).proposal(1).status == "answered"


def test_a_rewrite_failing_the_guard_four_times_fails_and_leaves_the_report(monkeypatch, fake):
    sid = saved()
    before = store.load(sid).report
    editor_desk.start(sid, "p1", "?")
    rethink_to(monkeypatch)
    bad = RevisedPoint(headline="AI use reached 41% of firms.", body="41%.", fact_ids=["A2"])
    fake.script = [parsed(bad) for _ in range(4)]
    editor_desk.rethink(sid, 1, llm.Meter())
    s = store.load(sid)
    assert s.proposal(1).status == "failed" and "41%" in s.proposal(1).error
    assert s.report == before
    models = [c[1]["model"] for c in fake.calls]
    assert models == ["anthropic/claude-haiku-5.5"] * 2 + ["anthropic/claude-sonnet-5.5"] * 2


def test_approve_changes_only_that_point_once(monkeypatch, fake):
    sid = asked_and_rethought(monkeypatch, fake)
    before = store.load(sid).report.points
    editor_desk.approve(sid, 1)
    s = store.load(sid)
    after = s.report.points
    assert after[1] == before[1] and after[2] == before[2]
    assert after[0].version == 2 and after[0].body.endswith("9.7%.")
    assert s.proposal(1).status == "approved"
    assert s.agent("A").transcript[-1]["content"].startswith("The analyst approved")
    with pytest.raises(Busy):
        editor_desk.approve(sid, 1)


def test_approve_after_the_point_moved_is_refused(monkeypatch, fake):
    sid = asked_and_rethought(monkeypatch, fake)
    with store.edit(sid) as x:
        x.report.points[0].version = 5
    with pytest.raises(Busy, match="changed"):
        editor_desk.approve(sid, 1)


def test_reject_keeps_the_report(monkeypatch, fake):
    sid = asked_and_rethought(monkeypatch, fake)
    before = store.load(sid).report
    editor_desk.reject(sid, 1)
    s = store.load(sid)
    assert s.report == before and s.proposal(1).status == "rejected"
    assert "rejected" in s.agent("A").transcript[-1]["content"]


def test_start_refuses_past_the_cost_cap():
    sid = saved()
    with store.edit(sid) as x:
        x.cost_usd = 7.95
    with pytest.raises(Busy, match="Cost cap"):
        editor_desk.start(sid, "p1", "?")
