from datetime import UTC, datetime

from castelino.agents.research.deep.models import (
    DeepResearchReport,
    ResearchSession,
    ResearchStatus,
    SourceRef,
    SubFinding,
)


def test_source_ref_roundtrip():
    s = SourceRef(title="Fed minutes", url="https://x.com/a", snippet="...")
    assert s.url == "https://x.com/a"


def test_session_defaults_and_serialization():
    sess = ResearchSession(
        id="abc123",
        original_query="will the fed cut?",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert sess.status == ResearchStatus.CREATED
    assert sess.reworded_query == ""
    assert sess.clarifying_questions == []
    assert sess.sonar_calls_used == 0
    # round-trips through JSON cleanly (used by the disk store)
    blob = sess.model_dump_json()
    again = ResearchSession.model_validate_json(blob)
    assert again.id == "abc123"


def test_report_construction():
    rep = DeepResearchReport(
        exec_summary="summary",
        findings=[SubFinding(sub_question_id="q1", summary="f", key_points=["p"])],
        sources=[SourceRef(title="t", url="u", snippet="s")],
        confidence=0.7,
    )
    assert rep.findings[0].sub_question_id == "q1"
    assert rep.confidence == 0.7
