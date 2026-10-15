"""The step runner's retry and round rules, with the agents faked at module level."""

import pytest

from castelino.agents.trade import (
    chartist,
    desks,
    editor,
    llm,
    orchestrator,
    publish,
    runner,
    store,
    talk,
)
from castelino.agents.trade.models import (
    Brief,
    DeskReport,
    DeskRun,
    ResearchItem,
    StepError,
    TalkMessage,
)
from tests.test_trade_editor import idea as sample
from tests.test_trade_editor import report
from tests.trade_fakes import fact

BRIEF = Brief(desk="news_1", title="t", brief="b", must_answer=[], item_ids=[], tickers=[])


@pytest.fixture
def iid(monkeypatch, tmp_path):
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    i = sample().model_copy(update={"id": "i1", "status": "awaiting_view"})
    store.save(i)
    return i.id


def test_research_retry_keeps_the_desks_it_already_ran(iid, monkeypatch):
    calls = []
    run = DeskRun(
        desk="news_1", brief=BRIEF, report=DeskReport(findings=[], summary="s", unanswered=[])
    )
    monkeypatch.setattr(orchestrator, "plan", lambda idea, m: calls.append("plan") or [BRIEF])
    monkeypatch.setattr(
        desks, "run", lambda idea, b, m: calls.append("desks") or ([run], [fact("A1", "x", [1.0])])
    )

    def propose(idea, m):
        calls.append("charts")
        if calls.count("charts") == 1:
            raise StepError("chart agent down")
        return [], []

    monkeypatch.setattr(chartist, "propose", propose)
    with pytest.raises(StepError):
        runner._research(iid, llm.Meter())
    runner._research(iid, llm.Meter())
    assert calls == ["plan", "desks", "charts", "charts"]
    assert [f.id for f in store.load(iid).facts].count("A1") == 1


def test_write_retry_after_a_failed_push_keeps_the_report(iid, monkeypatch):
    calls = []
    monkeypatch.setattr(
        editor, "write", lambda idea, m, base_draft=None: calls.append(1) or report()
    )
    pushes = iter([RuntimeError("Substack down"), {"draft_id": 7, "url": "u", "sha": "h"}])

    def push(idea):
        r = next(pushes)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(publish, "push", push)
    with pytest.raises(RuntimeError):
        runner._write(iid, llm.Meter())
    runner._write(iid, llm.Meter())
    assert calls == [1] and store.load(iid).status == "draft_ready"


def test_round_two_stops_before_the_editor_when_the_draft_is_published(iid, monkeypatch):
    with store.edit(iid) as i:
        i.round, i.substack = 2, {"draft_id": 7, "url": "u"}
    monkeypatch.setattr(
        publish, "_get", lambda draft_id: {"is_published": True, "draft_body": "{}"}
    )
    monkeypatch.setattr(editor, "write", lambda *a, **k: pytest.fail("the editor ran"))
    with pytest.raises(StepError, match="already published"):
        runner._write(iid, llm.Meter())


def test_round_two_with_a_deleted_draft_writes_without_a_base(iid, monkeypatch):
    with store.edit(iid) as i:
        i.round, i.substack = 2, {"draft_id": 7, "url": "u"}
    seen = []
    monkeypatch.setattr(publish, "_get", lambda draft_id: None)  # 404: deleted in Substack
    monkeypatch.setattr(
        editor, "write", lambda idea, m, base_draft=None: seen.append(base_draft) or report()
    )
    monkeypatch.setattr(publish, "push", lambda idea: {"draft_id": 8, "url": "u8", "sha": "h"})
    runner._write(iid, llm.Meter())
    assert seen == [None] and store.load(iid).substack["draft_id"] == 8


def _edit_reply(idea, t, to, message, meter):
    msgs = [
        TalkMessage(talk=t, role="user", text=message, at="x"),
        TalkMessage(talk=t, role="agent", text="Done.", at="x", action="edit"),
    ]
    return msgs, None, ("bear", "lead with the rupee")


@pytest.fixture
def ready(iid, monkeypatch):
    with store.edit(iid) as i:
        i.status, i.report = "draft_ready", report()
        i.substack = {"draft_id": 7, "url": "u", "sha": publish.sha("pushed text")}
    monkeypatch.setattr(talk, "reply", _edit_reply)
    monkeypatch.setattr(editor, "revise", lambda idea, part, ask, m: report(watch="Revised."))
    return iid


def test_talk_two_edit_saves_a_recreated_draft(ready, monkeypatch):
    monkeypatch.setattr(publish, "_get", lambda draft_id: None)  # deleted, so nothing to overwrite
    monkeypatch.setattr(publish, "push", lambda idea: {"draft_id": 9, "url": "u9", "sha": "h9"})
    runner.say(ready, 2, "Editor", "lead with the rupee")
    got = store.load(ready)
    assert got.substack == {"draft_id": 9, "url": "u9", "sha": "h9"}
    assert got.report.what_to_watch == "Revised."


def test_talk_two_edit_refuses_to_overwrite_hand_edits(ready, monkeypatch):
    body = '{"content": [{"type": "paragraph", "content": [{"type": "text", "text": "My own words."}]}]}'
    monkeypatch.setattr(publish, "_get", lambda draft_id: {"draft_body": body})
    monkeypatch.setattr(publish, "push", lambda idea: pytest.fail("pushed over the hand edits"))
    msgs = runner.say(ready, 2, "Editor", "lead with the rupee")
    assert "edited the Substack draft" in msgs[-1].text and msgs[-1].action == ""
    assert store.load(ready).report.what_to_watch == "Watch the rupee."


def test_start_round_over_the_cap_keeps_the_round(iid, monkeypatch):
    with store.edit(iid) as i:
        i.status, i.cost_usd = "draft_ready", 4.9
        i.research = [ResearchItem(id="u1", kind="claim", text="x", round=2)]
    with pytest.raises(ValueError, match="Cost cap"):
        runner.start_round(iid)
    assert store.load(iid).round == 1
