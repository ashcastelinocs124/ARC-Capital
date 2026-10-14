from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from castelino import benchmark
from castelino.agents import base

TODAY = f"{datetime.now():%Y-%m-%d}"


def test_calls_and_actions_append_and_read_back():
    a = benchmark.record_call(
        "desk_chat", "gpt-6-luna", {"user": "q1"}, {"answer": "a1"}, started=0
    )
    b = benchmark.record_call("web_search", "gpt-6-luna", {"user": "q2"}, started=0, error="boom")
    benchmark.record_action("rate", call_id=a, rating="up", better="")
    calls = benchmark.read("calls", TODAY)
    assert [c["id"] for c in calls] == [a, b]  # two gzip members read as one stream
    assert calls[0]["output"] == {"answer": "a1"} and calls[1]["error"] == "boom"
    assert benchmark.read("actions", TODAY)[0] == {
        **benchmark.read("actions", TODAY)[0],
        "call_id": a,
    }


def test_a_failed_write_never_raises(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("ARC_BENCHMARK_DIR", str(blocker))  # mkdir under a file fails
    assert benchmark.record_call("x", "m", {}, started=0)  # still returns an id


class Reply(BaseModel):
    answer: str


class Echo(base.StructuredAgent[Reply]):
    name = "echo"
    output_schema = Reply
    tier = "fast"

    def system_prompt(self) -> str:
        return "sys"

    def user_prompt(self, **ctx) -> str:
        return f"q={ctx['q']}"


def test_every_agent_call_is_recorded_with_its_input(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register("Reply", lambda s, u: Reply(answer="hi"))
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    bot = Echo()
    assert bot(q="why").answer == "hi"
    (row,) = benchmark.read("calls", TODAY)
    assert row["id"] == bot.last_call_id and row["agent"] == "echo"
    assert row["input"] == {"system": "sys", "user": "q=why", "schema": "Reply"}
    assert row["output"] == {"answer": "hi"} and row["error"] is None


def test_a_failed_agent_call_is_recorded_then_raised(monkeypatch):
    fake = base.FakeLLMClient()

    def boom(s, u):
        raise RuntimeError("model down")

    fake.register("Reply", boom)
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    with pytest.raises(RuntimeError):
        Echo()(q="x")
    assert "model down" in benchmark.read("calls", TODAY)[0]["error"]


def test_chat_returns_its_call_and_ratings_are_kept(monkeypatch):
    from castelino.dashboard.endpoints import admin_desk
    from castelino.dashboard.main import app

    monkeypatch.setattr(admin_desk.desk, "chat", lambda day, agent, msgs: ("an answer", "a" * 16))
    monkeypatch.setattr(admin_desk, "_day_ok", lambda day: day)  # no note files needed
    c = TestClient(app)
    r = c.post(
        "/admin/desk/2026-10-13/editor/chat",
        json={"messages": [{"role": "user", "text": "why the 2y?"}]},
    )
    assert r.json() == {"answer": "an answer", "call_id": "a" * 16}
    ok = c.post(
        "/admin/desk/rate", json={"call_id": "a" * 16, "rating": "down", "better": "  say X "}
    )
    assert ok.status_code == 200
    bad = c.post("/admin/desk/rate", json={"call_id": "nope", "rating": "up"})
    assert bad.status_code == 400
    chat, rate = benchmark.read("actions", TODAY)
    assert (
        chat["action"] == "chat" and chat["text"] == "why the 2y?" and chat["call_id"] == "a" * 16
    )
    assert rate == {**rate, "action": "rate", "rating": "down", "better": "say X"}
