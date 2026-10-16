"""The step runner's retry and round rules, with the agents faked at module level."""

import pytest

from castelino.agents.trade import (
    chartist,
    decide,
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


HAIKU = "anthropic/claude-haiku-5.5"
SEEN: list = []  # the ideas talk.reply was given


def _reply(*edits):
    def reply(idea, t, to, message, meter, decide_fn=None):
        SEEN.append(idea)
        msgs = [
            TalkMessage(talk=t, role="user", to=to, text=message, at="x"),
            TalkMessage(talk=t, role="agent", to=to, text="Done.", at="x", action="edit"),
        ]
        return msgs, None, list(edits)

    return reply


def _revise(idea, part, ask, meter):
    if part == "bear":
        raise StepError("The edit failed the number check: 9.9%")
    secs = [
        s.model_copy(update={"paragraphs": [f"{part} edited."]}) if s.key == part else s
        for s in idea.report.sections
    ]
    return idea.report.model_copy(update={"sections": secs}), HAIKU


@pytest.fixture
def ready(iid, monkeypatch):
    """A drafted idea whose Talk 2 job runs inline instead of on a thread."""
    with store.edit(iid) as i:
        i.status, i.report = "draft_ready", report()
        i.substack = {"draft_id": 7, "url": "u", "sha": publish.sha("pushed text")}
    SEEN.clear()
    monkeypatch.setattr(
        runner, "submit", lambda idea_id, step, sync=False: runner._run(idea_id, step)
    )
    monkeypatch.setattr(decide, "decide", lambda ctx, msg, names, meter: {"edit": 1.0})
    monkeypatch.setattr(talk, "reply", _reply(("bull", "open with valuation")))
    monkeypatch.setattr(editor, "revise", _revise)
    monkeypatch.setattr(publish, "_get", lambda draft_id: None)  # deleted, so nothing to overwrite
    monkeypatch.setattr(publish, "push", lambda idea: {"draft_id": 9, "url": "u9", "sha": "h9"})
    return iid


def test_talk_two_runs_as_a_job_and_saves_the_edit_with_its_trail(ready):
    """Talk 2 is an assistant, not rounds: the message runs as a job that edits, pushes and says how."""
    runner.say(ready, 2, "ARC", "open the bull case with valuation")
    got = store.load(ready)
    assert got.job.step == "talk" and got.job.state == "done" and got.status == "draft_ready"
    assert got.report.sections[0].paragraphs == ["bull edited."]
    assert got.substack == {"draft_id": 9, "url": "u9", "sha": "h9"}
    ask, ans = got.talk[-2:]
    assert (ask.role, ask.text, ans.role) == ("user", "open the bull case with valuation", "agent")
    assert any(s.startswith("Edited The bull case · Claude Haiku 5.5") for s in ans.trail)
    assert ans.trail[-1] == "Draft updated in Substack"


def test_talk_two_edits_every_section_asked_and_says_which_failed(ready, monkeypatch):
    monkeypatch.setattr(talk, "reply", _reply(("bull", "x"), ("bear", "x"), ("read", "x")))
    pushes = []
    monkeypatch.setattr(publish, "push", lambda idea: pushes.append(idea) or {"draft_id": 9})
    runner.say(ready, 2, "ARC", "open bull, bear and our read with valuation")
    got = store.load(ready)
    paras = {s.key: s.paragraphs for s in got.report.sections}
    assert paras["bull"] == ["bull edited."] and paras["read"] == ["read edited."]
    assert paras["bear"] == ["INDA fell 13.0%."] and len(pushes) == 1
    assert any("The bear case" in s and "9.9%" in s for s in got.talk[-1].trail)


def test_talk_two_searches_first_when_the_message_needs_new_facts(ready, monkeypatch):
    found = [fact("Q1.1", "The RBI held rates at 5.5%.", [5.5], "https://rbi.org.in/a")]
    run = DeskRun(desk="talk", brief=BRIEF, calls=2, domains=["rbi.org.in"])
    monkeypatch.setattr(decide, "decide", lambda ctx, msg, names, meter: {"research": 1.0})
    monkeypatch.setattr(desks, "ask", lambda idea, q, meter: (run, found))
    monkeypatch.setattr(talk, "reply", _reply())
    runner.say(ready, 2, "ARC", "What did the RBI say this week?")
    got = store.load(ready)
    assert "Q1.1" in {f.id for f in got.facts} and "Q1.1" in SEEN[-1].fact_map()
    assert got.talk[-1].trail[0].startswith("Searched 1 source: rbi.org.in · added Q1.1")


def test_talk_two_edit_refuses_to_overwrite_hand_edits(ready, monkeypatch):
    body = '{"content": [{"type": "paragraph", "content": [{"type": "text", "text": "My own words."}]}]}'
    monkeypatch.setattr(publish, "_get", lambda draft_id: {"draft_body": body})
    monkeypatch.setattr(publish, "push", lambda idea: pytest.fail("pushed over the hand edits"))
    runner.say(ready, 2, "ARC", "open the bull case with valuation")
    got = store.load(ready)
    assert "edited the Substack draft" in got.talk[-1].text and got.talk[-1].action == ""
    assert got.report.sections[0].paragraphs == ["INDA fell 13.0%."]
