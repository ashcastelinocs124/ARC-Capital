import base64
import functools

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from castelino.agents.trade import runner, store, talk
from castelino.agents.trade.models import (
    SECTIONS,
    ChartOption,
    ChartSpec,
    ResearchItem,
    TalkMessage,
)
from castelino.dashboard.endpoints import trade
from tests.test_trade_editor import idea as sample
from tests.test_trade_editor import report

FORMS = {
    "intro": "quadrant",
    "bull": "slope",
    "bear": "waterfall",
    "question": "bars",
    "technical": "dial",
    "read": "compare",
    "watch": "threshold_band",
}


def frame_debate(idea_id, meter):
    with store.edit(idea_id) as i:
        s = sample()
        i.frame, i.turns, i.facts, i.status = s.frame, s.turns, s.facts, "awaiting_view"
        i.research = [ResearchItem(id="m1", kind="moderator", text="Does selling slow?", round=1)]
    meter.add(0.2)


def research(idea_id, meter):
    with store.edit(idea_id) as i:
        rnd = i.current()
        for s, f in FORMS.items():
            spec = ChartSpec(
                section=s,
                form=f,
                series=["yahoo:INDA"],
                window_days=365,
                threshold=None,
                title=s,
                why="w",
                agent_pick=True,
            )
            rnd.options.append(
                ChartOption(id=f"{s}-{i.round}-1", spec=spec, file=f"{s}-{i.round}-1.png")
            )
        rnd.options.append(ChartOption(id="bull-1-9", spec=rnd.options[1].spec, error="no data"))
        i.status = "awaiting_charts"


def write(idea_id, meter):
    with store.edit(idea_id) as i:
        i.report = report()
        i.substack = {"draft_id": 1, "url": "https://pub/publish/post/1"}
        i.status = "draft_ready"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    steps = {
        "frame_debate": frame_debate,
        "rerun_debate": frame_debate,
        "research": research,
        "write": write,
    }
    monkeypatch.setattr(runner, "STEPS", steps)
    monkeypatch.setattr(runner, "submit", functools.partial(runner.submit, sync=True))
    app = FastAPI()
    app.include_router(trade.router)
    return TestClient(app)


def new(client):
    r = client.post("/admin/desk/trade", json={"idea": "India is a good AI diversification trade"})
    assert r.status_code == 200
    return r.json()["id"]


def picks():
    return {s: f"{s}-1-1" for s in SECTIONS}


def test_full_round_trip(client):
    iid = new(client)
    got = client.get(f"/admin/desk/trade/{iid}").json()
    assert got["status"] == "awaiting_view" and got["job"]["state"] == "done"
    assert got["cost_usd"] == pytest.approx(0.2)
    assert client.post(f"/admin/desk/trade/{iid}/research").json()["status"] == "awaiting_charts"
    r = client.post(f"/admin/desk/trade/{iid}/charts", json={"picks": picks()})
    assert r.json()["status"] == "draft_ready"
    listed = client.get("/admin/desk/trade").json()["ideas"]
    assert listed[0]["id"] == iid and listed[0]["status"] == "draft_ready"


def test_picks_rejects_missing_section_and_undrawn_option(client):
    iid = new(client)
    client.post(f"/admin/desk/trade/{iid}/research")
    p = picks()
    del p["watch"]
    r = client.post(f"/admin/desk/trade/{iid}/charts", json={"picks": p})
    assert r.status_code == 400 and "watch" in r.json()["detail"]
    r = client.post(
        f"/admin/desk/trade/{iid}/charts", json={"picks": {**picks(), "bull": "bull-1-9"}}
    )
    assert r.status_code == 400 and "could not be drawn" in r.json()["detail"]
    assert store.load(iid).status == "awaiting_charts"


def test_cost_cap_blocks_the_step(client):
    iid = new(client)
    with store.edit(iid) as i:
        i.cost_usd = 4.5
    job = client.post(f"/admin/desk/trade/{iid}/research").json()["job"]
    assert job["state"] == "failed" and job["message"].startswith("Cost cap")


def test_busy_idea_is_409(client):
    iid = new(client)
    with store.edit(iid) as i:
        i.job = i.job.model_copy(update={"state": "running"})
    assert client.post(f"/admin/desk/trade/{iid}/research").status_code == 409


def test_failed_step_retries_and_interrupted_recovers(client, monkeypatch):
    iid = new(client)
    calls = []

    def flaky(idea_id, meter):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("desk down")
        research(idea_id, meter)

    monkeypatch.setitem(runner.STEPS, "research", flaky)
    job = client.post(f"/admin/desk/trade/{iid}/research").json()["job"]
    assert job["state"] == "failed" and "desk down" in job["message"]
    assert client.post(f"/admin/desk/trade/{iid}/retry").json()["status"] == "awaiting_charts"
    with store.edit(iid) as i:
        i.job = i.job.model_copy(update={"state": "running"})
    assert runner.recover_interrupted() == 1 and store.load(iid).job.state == "interrupted"


def test_talk_only_at_the_two_talk_points(client, monkeypatch):
    iid = new(client)
    r = client.post(f"/admin/desk/trade/{iid}/talk", json={"talk": 2, "message": "hi"})
    assert r.status_code == 400

    def fake_reply(idea, t, to, message, meter):
        msgs = [
            TalkMessage(talk=t, role="user", text=message, at="x"),
            TalkMessage(talk=t, role="agent", text="ok", at="x", action="research"),
        ]
        return msgs, ResearchItem(id="u1", kind="claim", text="RBI defends 95", round=1), None

    monkeypatch.setattr(talk, "reply", fake_reply)
    body = {"talk": 1, "to": "Bear", "message": "RBI defends 95"}
    r = client.post(f"/admin/desk/trade/{iid}/talk", json=body)
    assert r.status_code == 200 and [m["text"] for m in r.json()["messages"]] == [
        "RBI defends 95",
        "ok",
    ]
    assert [x.id for x in store.load(iid).research] == ["m1", "u1"]
    assert client.delete(f"/admin/desk/trade/{iid}/research/u1").status_code == 200
    assert store.load(iid).research[1].removed


def test_bad_chart_name_and_unknown_idea_are_404(client):
    iid = new(client)
    assert client.get(f"/admin/desk/trade/{iid}/charts/..%2Fidea.json").status_code == 404
    assert client.get("/admin/desk/trade/nope").status_code == 404


def test_desk_app_requires_the_password(monkeypatch, tmp_path):
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    monkeypatch.setenv("ADMIN_PASSWORD", "pw")
    from castelino.dashboard import desk_app

    c = TestClient(desk_app.app)
    assert c.get("/admin/desk/trade").status_code == 401
    auth = {"Authorization": "Basic " + base64.b64encode(b"x:pw").decode()}
    assert c.get("/admin/desk/trade", headers=auth).json() == {"ideas": []}
