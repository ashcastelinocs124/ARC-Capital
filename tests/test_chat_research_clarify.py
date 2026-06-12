"""Tests for deep research clarification flow in chat registry."""
from datetime import datetime, timezone

import castelino.agents.chat.registry as reg
from castelino.agents.research.deep.models import (
    ClarificationQuestion,
    DeepResearchReport,
    ResearchSession,
    ResearchStatus,
    SourceRef,
)


def _now():
    return datetime.now(timezone.utc)


def _make_session(status, report=None, questions=None, reworded="test"):
    return ResearchSession(
        id="test-123", original_query="test", reworded_query=reworded,
        clarifying_questions=questions or [],
        status=status, report=report,
        created_at=_now(), updated_at=_now(),
    )


class FakeOrch:
    def __init__(self, questions=None, fail=False):
        self._questions = questions or []
        self._fail = fail

    def start(self, query):
        return _make_session(
            ResearchStatus.AWAITING_ANSWERS if self._questions else ResearchStatus.RESEARCHING,
            reworded=query, questions=self._questions,
        )

    def run_first_round(self, session_id, answers=None):
        sess = _make_session(ResearchStatus.RESEARCHING)
        if self._fail:
            sess.status = ResearchStatus.FAILED
            sess.error = "all sub-agents failed"
        else:
            sess.status = ResearchStatus.SYNTHESIZING
        return sess

    def finish(self, session_id):
        return _make_session(
            ResearchStatus.COMPLETE,
            report=DeepResearchReport(
                exec_summary="Yield curve is steepening due to growth optimism.",
                full_answer="Detailed analysis...",
                sources=[], chart_specs=[], charts=[],
            ),
        )


def test_clear_pending():
    reg._research_pending_id = "abc"
    reg._clear_pending_research()
    assert reg._research_pending_id is None


def test_submit_no_pending():
    reg._clear_pending_research()
    assert "no pending" in reg._submit_research_answers("x").lower()


def test_research_with_questions(monkeypatch):
    reg._clear_pending_research()
    fake = FakeOrch(questions=[
        ClarificationQuestion(question="What timeframe?", why="Scopes analysis"),
        ClarificationQuestion(question="Which market?"),
    ])
    monkeypatch.setattr("castelino.agents.chat.registry.DeepResearchOrchestrator", lambda: fake)
    result = reg._research({"query": "yield curve"})
    assert "what timeframe" in result.lower()
    assert "scopes" in result.lower()
    assert reg._research_pending_id == "test-123"


def test_research_no_questions(monkeypatch):
    reg._clear_pending_research()
    monkeypatch.setattr("castelino.agents.chat.registry.DeepResearchOrchestrator", lambda: FakeOrch(questions=[]))
    result = reg._research({"query": "yield curve"})
    assert "Yield curve is steepening" in result
    assert reg._research_pending_id is None


def test_submit_answers_runs_and_clears(monkeypatch):
    reg._research_pending_id = "test-123"
    monkeypatch.setattr("castelino.agents.chat.registry.DeepResearchOrchestrator", lambda: FakeOrch())
    result = reg._submit_research_answers("3 months, US only")
    assert "Yield curve is steepening" in result
    assert reg._research_pending_id is None


def test_submit_answers_fail(monkeypatch):
    reg._research_pending_id = "test-fail"
    fake = FakeOrch(fail=True)
    monkeypatch.setattr("castelino.agents.chat.registry.DeepResearchOrchestrator", lambda: fake)
    result = reg._submit_research_answers("test")
    assert "failed" in result.lower()
    assert reg._research_pending_id is None


def test_format_report():
    sess = _make_session(
        ResearchStatus.COMPLETE,
        report=DeepResearchReport(
            exec_summary="Summary here.",
            full_answer="Full.",
            sources=[SourceRef(title="S1", url="https://a.com", snippet="s")],
            chart_specs=[], charts=[],
        ),
    )
    text = reg._format_report(sess)
    assert "Summary here" in text
    assert "https://a.com" in text
