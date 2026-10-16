from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from castelino import benchmark
from castelino.agents import chart_desk as desk
from castelino.agents.trade import forms, llm
from castelino.dashboard.endpoints import admin_desk
from castelino.dashboard.endpoints import chart_desk as charts_ep
from tests.test_trade_forms import SRC


def yahoo(t):
    if t == "EMPTY":
        raise ValueError("yfinance returned empty for EMPTY")
    return SRC.yahoo(t)


FAKE = forms.Sources(yahoo=yahoo, fred=SRC.fred, sectors=SRC.sectors)


def chart(form, *series, title="Japan lags the US"):
    return desk.ChartIdea(
        form=form, series=list(series), window_days=365, threshold=None, title=title, why="w"
    )


@pytest.fixture(autouse=True)
def tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_CHART_DESK_DIR", str(tmp_path / "chart_desk"))


def fake_llm(monkeypatch, answers):
    """answers: model -> list of Proposals (one per call) or an Exception. Records what was sent."""
    sent = []

    def structured(agent, model, messages, schema, meter, *, fallback=None):
        sent.append((model, messages))
        a = answers[model]
        if isinstance(a, Exception):
            raise a
        meter.add(0.001)
        return a.pop(0)

    monkeypatch.setattr(llm, "structured", structured)
    return sent


def test_chat_draws_retries_failures_and_sends_the_thread_back(monkeypatch):
    first = desk.Proposal(
        reply="Two angles.",
        charts=[
            chart("compare", "yahoo:EWJ", "yahoo:SPY"),
            chart("line", "yahoo:EMPTY"),  # no data → failed, retried
            chart("line", "bad id"),  # fails the spec check
        ],
    )
    retry = desk.Proposal(reply="", charts=[chart("underwater", "yahoo:EWJ", "yahoo:SPY")])
    later = desk.Proposal(reply="Swapped.", charts=[chart("line", "yahoo:FXY")])
    sent = fake_llm(monkeypatch, {"gpt-6-luna": [first, retry, later]})

    run = desk.chat("Is the yen carry trade unwinding?", None, None, sync=True, src=FAKE)
    reply = run.turns[0].replies[0]
    assert (reply.model, reply.state, reply.text) == ("gpt-6-luna", "done", "Two angles.")
    assert [c.form for c in reply.charts if c.file] == ["compare", "underwater"]
    errors = [c.error for c in reply.charts if c.error]
    assert "empty" in errors[0] and "bad series" in errors[1]
    assert "couldn't be drawn" in sent[1][1][-1]["content"]  # the retry is told why
    assert reply.usd == pytest.approx(0.002)
    assert (desk.run_dir(run.id) / reply.charts[0].file).exists()

    run = desk.chat("Swap the calendar for the yen", None, run.id, sync=True, src=FAKE)
    history = sent[-1][1]
    assert history[1] == {"role": "user", "content": "Is the yen carry trade unwinding?"}
    assert "compare yahoo:EWJ, yahoo:SPY" in history[2]["content"]  # earlier charts' specs
    assert len(run.turns) == 2 and run.turns[1].replies[0].charts[0].file


def test_compare_keeps_a_failing_model_from_breaking_the_others_and_tallies_votes(monkeypatch):
    good = desk.Proposal(reply="ok", charts=[chart("line", "yahoo:EWJ")])
    fake_llm(monkeypatch, {"gpt-6-luna": [good], "z-ai/glm-5.3": RuntimeError("no parsed object")})

    run = desk.compare("Yen?", ["gpt-6-luna", "z-ai/glm-5.3"], sync=True, src=FAKE)
    a, b = run.turns[0].replies
    assert (a.state, len(a.charts)) == ("done", 1)
    assert (b.state, b.error) == ("failed", "no parsed object")

    desk.vote(run.id, "gpt-6-luna")
    assert desk.scoreboard() == {"gpt-6-luna": 1}
    assert desk.load(run.id).vote == "gpt-6-luna"
    assert desk.vote(run.id, "gpt-6-luna").vote is None  # a second click takes the vote back
    assert benchmark.read("actions", f"{datetime.now():%Y-%m-%d}")[-1]["action"] == "chart_vote"
    with pytest.raises(ValueError):
        desk.vote(run.id, "not-in-this-run")
    with pytest.raises(ValueError):
        desk.check_models(["ok-model", "rm -rf /"])


def test_charts_routes_are_not_taken_by_the_daily_desk_day_route(monkeypatch):
    fake_llm(monkeypatch, {"gpt-6-luna": [desk.Proposal(reply="r", charts=[])]})
    app = FastAPI()
    app.include_router(charts_ep.router)
    app.include_router(admin_desk.router)
    c = TestClient(app)
    body = c.get("/admin/desk/charts").json()
    assert body["chat_model"] == "gpt-6-luna" and body["runs"] == []
    assert body["compare_default"][0] == "gpt-6-luna"
    assert c.get("/admin/desk/charts/0123456789").status_code == 404
    assert c.get("/admin/desk/charts/../../etc").status_code == 404
