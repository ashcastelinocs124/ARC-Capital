import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from castelino.agents.research.deep import clarifier, runner, store
from castelino.agents.research.deep.models import (
    Clarification,
    ClarifyQuestion,
    Point,
    ResearchReport,
)
from castelino.dashboard.endpoints import deep_research
from tests.research_fakes import agent

BASE = "/admin/desk/research"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))
    qs = [
        ClarifyQuestion(question="US only?", why="scope"),
        ClarifyQuestion(question="Since when?", why="window"),
    ]
    monkeypatch.setattr(
        clarifier,
        "clarify",
        lambda topic, meter: Clarification(
            question="How fast are US firms adopting AI?", questions=qs
        ),
    )
    calls = []
    monkeypatch.setattr(runner, "submit", lambda sid, step="run", **k: calls.append((sid, step)))
    monkeypatch.setattr(runner, "submit_ask", lambda sid, n, **k: calls.append((sid, f"ask{n}")))
    app = FastAPI()
    app.include_router(deep_research.router)
    c = TestClient(app)
    c.calls = calls
    return c


def new(client) -> str:
    return client.post(BASE, json={"topic": "AI adoption"}).json()["id"]


def test_create_runs_the_clarifier(client):
    r = client.post(BASE, json={"topic": "AI adoption"})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "awaiting_answers"
    assert len(body["clarifying_questions"]) == 2 and body["cost_cap_usd"] == 8.0
    assert client.get(BASE).json()["sessions"][0]["topic"] == "AI adoption"


def test_answers_drop_blanks_and_start_the_run(client):
    sid = new(client)
    answers = {"US only?": "  ", "Since when?": " since 2022 "}
    r = client.post(f"{BASE}/{sid}/answers", json={"answers": answers})
    assert r.json()["answers"] == {"Since when?": "since 2022"}
    assert r.json()["status"] == "researching" and client.calls == [(sid, "run")]
    assert client.post(f"{BASE}/{sid}/answers", json={"answers": {}}).status_code == 409


def test_transcripts_never_leave_the_server(client):
    sid = new(client)
    with store.edit(sid) as x:
        x.agents = [agent("A", transcript=[{"role": "user", "content": "secret prompt"}])]
    assert "transcript" not in client.get(f"{BASE}/{sid}").json()["agents"][0]


def test_ask_approve_reject_routes(client):
    sid = new(client)
    with store.edit(sid) as x:
        x.agents = [agent("A")]
        x.report = ResearchReport(
            title="t",
            subtitle="s",
            points=[Point(id="p1", agent="A", headline="h", body="b", fact_ids=["A1"])],
        )
        x.status = "complete"
    assert client.post(f"{BASE}/{sid}/points/p9/ask", json={"text": "?"}).status_code == 404
    r = client.post(f"{BASE}/{sid}/points/p1/ask", json={"text": "Is it current?"})
    assert r.status_code == 200 and r.json()["proposals"][0]["status"] == "running"
    assert client.calls[-1] == (sid, "ask1")
    assert client.post(f"{BASE}/{sid}/points/p1/ask", json={"text": "again"}).status_code == 409
    assert client.post(f"{BASE}/{sid}/proposals/1/approve").status_code == 409  # still running
    assert client.post(f"{BASE}/{sid}/proposals/9/reject").status_code == 404
    assert client.get(f"{BASE}/nope").status_code == 404


def test_retry_needs_a_failed_step(client):
    assert client.post(f"{BASE}/{new(client)}/retry").status_code == 409


def test_only_the_admin_routes_exist():
    from castelino.dashboard import desk_app, main

    for app in (main.app, desk_app.app):
        paths = {r.path for r in app.routes}
        assert BASE in paths and "/research/start" not in paths
