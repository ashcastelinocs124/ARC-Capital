from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import (
    DeepResearchReport,
    ReflectionResult,
    SourceRef,
    SubFinding,
)
from castelino.agents.research.deep.synthesizer import Synthesizer


def _llm():
    fake = FakeLLMClient()
    fake.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="The Fed is likely to hold.", confidence=0.6,
        sources=[SourceRef(title="t", url="u")],
    ))
    fake.register("ReflectionResult", lambda s, u: ReflectionResult(
        is_sufficient=True, gaps=[],
    ))
    return fake


def test_synthesize_builds_report():
    syn = Synthesizer(llm=_llm())
    findings = [SubFinding(sub_question_id="q1", summary="held last time")]
    report = syn.synthesize(reworded_query="Will the Fed hold?", findings=findings)
    assert "Fed" in report.exec_summary
    # findings are attached to the report by the synthesizer
    assert report.findings == findings


def test_reflect_returns_sufficiency():
    syn = Synthesizer(llm=_llm())
    refl = syn.reflect(
        reworded_query="Will the Fed hold?",
        report=DeepResearchReport(exec_summary="x"),
        round_num=1,
    )
    assert refl.is_sufficient is True
