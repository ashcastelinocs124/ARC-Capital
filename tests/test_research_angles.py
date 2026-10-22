import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from castelino.agents.research.deep import charts, lead, runner, store, sub_agent, synthesizer
from castelino.agents.research.deep.models import (
    Addition,
    Brief,
    ChartValue,
    Clarification,
    Finding,
    Job,
    MorePoints,
    Plan,
    Point,
    PointChart,
    PointDraft,
    ResearchReport,
    StepError,
)
from castelino.agents.trade import llm
from castelino.dashboard.endpoints import deep_research
from tests.research_fakes import agent, brief, fact
from tests.trade_fakes import FakeClient, parsed

TOPICS = "How companies use AI models; frontier vs open models; interest in local or sovereign AI"


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))


def report_session(**extra):
    s = store.create(
        "AI adoption", Clarification(question="How fast are firms adopting AI?", questions=[])
    )
    points = [
        Point(
            id="p1",
            agent="A",
            headline="AI use reached 9.2% of firms.",
            body="9.2%.",
            fact_ids=["A1"],
        ),
        Point(
            id="p2", agent="B", headline="Large firms lead at 27%.", body="27%.", fact_ids=["B1"]
        ),
    ]
    with store.edit(s.id) as x:
        x.agents = [
            agent("A"),
            agent("B", facts=[fact("B1", "27% of large firms in 2026", [27.0])]),
        ]
        x.report = ResearchReport(title="t", subtitle="s", points=points)
        x.status = "complete"
        for k, v in extra.items():
            setattr(x, k, v)
    return s.id


# ── Lead ────────────────────────────────────────────────────────────────────
def test_plan_angles_caps_at_3_and_lists_what_is_already_covered(monkeypatch):
    c = FakeClient(
        [parsed(Plan(briefs=[Brief(name=f"n{i}", angle="?", brief="b") for i in range(5)]))]
    )
    monkeypatch.setattr(llm, "_client", lambda m: c)
    out = lead.plan_angles(store.load(report_session()), TOPICS, llm.Meter())
    user = c.calls[0][1]["messages"][1]["content"]
    assert len(out) == 3 and TOPICS in user
    assert "A · Adoption rate" in user and "AI use reached 9.2% of firms." in user


# ── Writer ──────────────────────────────────────────────────────────────────
class FakeEditor:
    def __init__(self, *outs):
        self.outs, self.calls, self.last_usage = list(outs), [], (800, 300)

    def parse(self, *, system, messages, schema):
        self.calls.append((system, list(messages), schema))
        return self.outs.pop(0), []


def with_new_agent():
    sid = report_session()
    c = agent(
        "C",
        facts=[fact("C1", "38% of firms use frontier models via API in 2026", [38.0])],
        round_=3,
    )
    with store.edit(sid) as x:
        x.agents.append(c)
    return store.load(sid)


def test_write_more_writes_only_new_points_for_the_new_agents():
    s = with_new_agent()
    good = MorePoints(
        points=[
            PointDraft(
                agent="C", headline="38% use frontier models.", body="38% [C1].", fact_ids=["C1"]
            )
        ]
    )
    ed = FakeEditor(good)
    pts, _ = synthesizer.write_more(s, ["C"], 1, llm.Meter(), client=ed)
    assert [(p.id, p.agent, p.added, p.body) for p in pts] == [("p3", "C", 1, "38%.")]
    system, msgs, schema = ed.calls[0]
    assert (
        schema is MorePoints
        and "Researcher C" in msgs[0]["content"]
        and "Researcher A" not in msgs[0]["content"]
    )
    assert "AI use reached 9.2% of firms." in msgs[0]["content"]  # told what's already covered


def test_write_more_retries_once_then_fails():
    s = with_new_agent()
    wrong_owner = MorePoints(
        points=[PointDraft(agent="A", headline="h", body="38%.", fact_ids=["C1"])]
    )
    bad_number = MorePoints(
        points=[PointDraft(agent="C", headline="h", body="41%.", fact_ids=["C1"])]
    )
    with pytest.raises(StepError):
        synthesizer.write_more(s, ["C"], 1, llm.Meter(), client=FakeEditor(wrong_owner, bad_number))


# ── Runner ──────────────────────────────────────────────────────────────────
def test_the_add_step_researches_the_angles_and_appends_charted_points(monkeypatch):
    sid = report_session(additions=[Addition(n=1, text=TOPICS, round=3, created_at="x")])
    before = store.load(sid).report.points
    monkeypatch.setattr(
        lead, "plan_angles", lambda s, text, m: [brief("Frontier models"), brief("Sovereign AI")]
    )

    def research(ar, question, board, budget, meter):
        f = fact(f"{ar.letter}1", "38% of firms", [38.0])
        return ar.model_copy(
            update={"facts": [f], "findings": [Finding(id="f", claim="c", fact_ids=[f.id])]}
        )

    monkeypatch.setattr(sub_agent, "research", research)

    def more(s, letters, added, meter, ask=""):
        assert letters == ["C", "D"] and ask == TOPICS
        return [
            Point(
                id="p3",
                agent="C",
                headline="38% use frontier models.",
                body="38%.",
                fact_ids=["C1"],
                added=added,
            )
        ], "end"

    monkeypatch.setattr(synthesizer, "write_more", more)
    one = [ChartValue(fact_id="C1", label="firms", value=38.0)]
    monkeypatch.setattr(
        charts,
        "chart_points",
        lambda pts, by, m: {p.id: PointChart(form="stat", title="t", values=one) for p in pts},
    )
    runner.submit(sid, "add", sync=True)
    s = store.load(sid)
    assert s.job.state == "done" and s.status == "complete" and s.additions[0].status == "done"
    assert [(a.letter, a.round) for a in s.agents[2:]] == [("C", 3), ("D", 3)]
    assert s.report.points[:2] == before and s.report.points[2].chart.values[0].value == 38.0


# ── API ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "submit", lambda sid, step="run", **k: calls.append((sid, step)))
    app = FastAPI()
    app.include_router(deep_research.router)
    c = TestClient(app)
    c.calls = calls
    return c


def test_angles_route_starts_an_add_step(client):
    sid = report_session()
    r = client.post(f"/admin/desk/research/{sid}/angles", json={"text": f"  {TOPICS} "})
    assert r.status_code == 200 and client.calls == [(sid, "add")]
    add = r.json()["additions"][0]
    assert (add["n"], add["text"], add["round"], add["status"]) == (1, TOPICS, 3, "running")
    assert (
        client.post(f"/admin/desk/research/{sid}/angles", json={"text": "more"}).status_code == 409
    )


def test_angles_need_a_finished_idle_report(client):
    unfinished = store.create("x", Clarification(question="q", questions=[])).id
    assert (
        client.post(f"/admin/desk/research/{unfinished}/angles", json={"text": TOPICS}).status_code
        == 409
    )
    busy = report_session(job=Job(step="run", state="running", at="x"))
    assert (
        client.post(f"/admin/desk/research/{busy}/angles", json={"text": TOPICS}).status_code == 409
    )


def test_a_failed_add_marks_its_addition_and_a_new_request_is_allowed(client, monkeypatch):
    sid = report_session(additions=[Addition(n=1, text=TOPICS, round=3, created_at="x")])
    monkeypatch.setattr(lead, "plan_angles", lambda s, text, m: [brief("Frontier models")])
    monkeypatch.setattr(
        sub_agent, "research", lambda ar, *a: ar.model_copy(update={"error": "boom"})
    )
    runner._execute(sid, "add")
    s = store.load(sid)
    assert (
        s.job.state == "failed"
        and s.additions[0].status == "failed"
        and "boom" in s.additions[0].error
    )
    assert len(s.report.points) == 2
    r = client.post(f"/admin/desk/research/{sid}/angles", json={"text": "sovereign AI"})
    assert r.status_code == 200 and r.json()["additions"][1]["round"] == 4


def test_the_cost_cap_fails_the_addition_at_once():
    sid = report_session(cost_usd=7.5)
    app = FastAPI()
    app.include_router(deep_research.router)
    r = TestClient(app).post(f"/admin/desk/research/{sid}/angles", json={"text": TOPICS})
    add = r.json()["additions"][0]
    assert add["status"] == "failed" and "Cost cap" in add["error"]


def test_a_restart_fails_a_running_addition():
    sid = report_session(additions=[Addition(n=1, text=TOPICS, round=3, created_at="x")])
    runner.recover_interrupted()
    assert store.load(sid).additions[0].status == "failed"


def test_write_more_sees_the_ask_and_says_where_the_points_go():
    s = with_new_agent()
    first = MorePoints(
        points=[PointDraft(agent="C", headline="What it is.", body="38% [C1].", fact_ids=["C1"])],
        place="start",
    )
    ed = FakeEditor(first)
    ask = "I want a point at the start explaining what frontier models are"
    pts, place = synthesizer.write_more(s, ["C"], 1, llm.Meter(), ask=ask, client=ed)
    assert place == "start" and [p.id for p in pts] == ["p3"]
    assert ask in ed.calls[0][1][0]["content"]  # the writer reads the analyst's own words


def test_an_addition_asked_for_at_the_start_opens_the_report(monkeypatch):
    sid = report_session(
        additions=[Addition(n=1, text="a point at the start", round=3, created_at="x")]
    )
    before = [p.id for p in store.load(sid).report.points]
    monkeypatch.setattr(lead, "plan_angles", lambda s, text, m: [brief("Definition")])

    def research(ar, question, board, budget, meter):
        f = fact(f"{ar.letter}1", "38% of firms", [38.0])
        return ar.model_copy(
            update={"facts": [f], "findings": [Finding(id="f", claim="c", fact_ids=[f.id])]}
        )

    monkeypatch.setattr(sub_agent, "research", research)
    new = Point(id="p3", agent="C", headline="What it is.", body="38%.", fact_ids=["C1"], added=1)
    monkeypatch.setattr(
        synthesizer, "write_more", lambda s, letters, added, meter, ask="": ([new], "start")
    )
    monkeypatch.setattr(charts, "chart_points", lambda pts, by, m: {})
    runner.submit(sid, "add", sync=True)
    assert [p.id for p in store.load(sid).report.points] == ["p3", *before]
