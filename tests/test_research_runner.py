import pytest

from castelino.agents.research.deep import (
    charts,
    critic,
    editor_desk,
    lead,
    runner,
    store,
    sub_agent,
    synthesizer,
)
from castelino.agents.research.deep.models import (
    Busy,
    ChartValue,
    Clarification,
    Critique,
    Finding,
    Job,
    Point,
    PointChart,
    Proposal,
    ResearchReport,
)
from tests.research_fakes import agent, brief, fact

CHARTED: list[list[str]] = []


def fake_charts(points, by, meter):
    CHARTED.append([p.id for p in points])
    one = [ChartValue(fact_id="A1", label="firms", value=9.2)]
    return {p.id: PointChart(form="stat", title=p.headline, unit="%", values=one) for p in points}


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))
    monkeypatch.setattr(charts, "chart_points", fake_charts)
    CHARTED.clear()


@pytest.fixture
def ran(monkeypatch):
    calls: list[str] = []

    def research(ar, question, board, budget, meter):
        calls.append(ar.letter)
        f = fact(f"{ar.letter}1", "9.2% of firms", [9.2])
        found = [Finding(id="f", claim="c", fact_ids=[f.id])]
        return ar.model_copy(update={"facts": [f], "findings": found, "error": None})

    report = ResearchReport(
        title="t",
        subtitle="s",
        points=[Point(id="p1", agent="A", headline="h", body="b", fact_ids=["A1"])],
    )
    monkeypatch.setattr(sub_agent, "research", research)
    monkeypatch.setattr(lead, "plan", lambda s, m: [brief("Adoption rate"), brief("Who leads")])
    monkeypatch.setattr(critic, "review", lambda s, m: Critique(done=True, gaps=[]))
    monkeypatch.setattr(synthesizer, "write", lambda s, m: report)
    return calls


def new_session():
    s = store.create("AI adoption", Clarification(question="Q?", questions=[]))
    with store.edit(s.id) as x:
        x.status = "researching"
    return s.id


def test_run_plans_researches_and_writes(ran):
    sid = new_session()
    runner.submit(sid, "run", sync=True)
    s = store.load(sid)
    assert s.status == "complete" and s.job.state == "done" and s.report.points[0].id == "p1"
    assert [a.letter for a in s.agents] == ["A", "B"] and ran == ["A", "B"]
    assert s.report.points[0].chart.form == "stat" and CHARTED == [["p1"]]


def test_the_charts_step_fills_only_points_without_a_chart():
    sid = new_session()
    drawn = PointChart(
        form="stat", title="t", values=[ChartValue(fact_id="A1", label="x", value=1.0)]
    )
    with store.edit(sid) as x:
        x.status = "complete"
        x.report = ResearchReport(
            title="t",
            subtitle="s",
            points=[
                Point(id="p1", agent="A", headline="h1", body="b", fact_ids=["A1"], chart=drawn),
                Point(id="p2", agent="A", headline="h2", body="b", fact_ids=["A1"]),
            ],
        )
    runner.submit(sid, "charts", sync=True)
    s = store.load(sid)
    assert CHARTED == [["p2"]] and s.job.state == "done"
    assert s.report.points[0].chart == drawn and s.report.points[1].chart.title == "h2"


def test_retry_keeps_agents_that_have_findings(ran, monkeypatch):
    sid = new_session()
    with store.edit(sid) as x:
        x.agents = [
            agent("A"),
            agent("B", facts=[], findings=[]).model_copy(update={"error": "timeout"}),
        ]
    monkeypatch.setattr(lead, "plan", lambda s, m: pytest.fail("planned again"))
    runner.submit(sid, "run", sync=True)
    assert ran == ["B"] and store.load(sid).status == "complete"


def test_every_agent_failing_fails_the_step(monkeypatch, ran):
    monkeypatch.setattr(
        sub_agent, "research", lambda ar, *a: ar.model_copy(update={"error": "boom"})
    )
    sid = new_session()
    runner.submit(sid, "run", sync=True)
    s = store.load(sid)
    assert s.job.state == "failed" and "Every research agent failed" in s.job.message
    assert "boom" in s.job.message


def test_gaps_add_one_round_with_the_next_letters(ran, monkeypatch):
    monkeypatch.setattr(
        critic, "review", lambda s, m: Critique(done=False, gaps=["no small-firm data"])
    )
    monkeypatch.setattr(lead, "plan_gaps", lambda s, gaps, m: [brief("Small firms")])
    sid = new_session()
    runner.submit(sid, "run", sync=True)
    s = store.load(sid)
    assert ran == ["A", "B", "C"] and s.agents[2].round == 2 and s.status == "complete"


def test_cost_cap_refuses_a_step_before_it_starts(ran):
    sid = new_session()
    with store.edit(sid) as x:
        x.cost_usd = 7.0
    runner.submit(sid, "run", sync=True)
    s = store.load(sid)
    assert s.job.state == "failed" and "Cost cap" in s.job.message and ran == []


def test_a_busy_session_refuses_a_second_step():
    sid = new_session()
    with store.edit(sid) as x:
        x.job = Job(step="run", state="running", at="x")
    with pytest.raises(Busy):
        runner.submit(sid, "run")


def _with_running_ask(sid):
    with store.edit(sid) as x:
        x.proposals = [
            Proposal(n=1, point_id="p1", agent="A", text="?", base_version=1, created_at="x")
        ]


def test_recover_marks_running_jobs_and_asks():
    sid = new_session()
    _with_running_ask(sid)
    with store.edit(sid) as x:
        x.job = Job(step="run", state="running", at="x")
    assert runner.recover_interrupted() == 1
    s = store.load(sid)
    assert s.job.state == "interrupted" and s.proposal(1).status == "failed"
    assert "restarted" in s.proposal(1).error


def test_a_failed_ask_shows_on_its_proposal(monkeypatch):
    sid = new_session()
    _with_running_ask(sid)

    def boom(sid, n, meter):
        raise RuntimeError("model down")

    monkeypatch.setattr(editor_desk, "rethink", boom)
    runner.submit_ask(sid, 1, sync=True)
    p = store.load(sid).proposal(1)
    assert p.status == "failed" and "model down" in p.error and p.trail[-1].startswith("Cost $")
