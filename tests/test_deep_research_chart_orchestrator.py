import pandas as pd
import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    ChartSpec,
    ChartType,
    ClarifierResult,
    DecompositionResult,
    DeepResearchReport,
    ReflectionResult,
    ResearchStatus,
    SubFinding,
    SubQuestion,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.store import ResearchStore


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_llm_client(None)


def _llm_with_chart():
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Q?", clarifying_questions=[]))
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id="q0", text="sub 0")]))
    llm.register("SubFinding", lambda s, u: SubFinding(
        sub_question_id="q0", summary="f", confidence=0.7))
    llm.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="answer", confidence=0.7,
        chart_specs=[ChartSpec(type=ChartType.YIELD_CURVE, title="curve")]))
    llm.register("ReflectionResult", lambda s, u: ReflectionResult(is_sufficient=True))
    return llm


class _FakeAdapter:
    def yield_curve(self):
        return pd.DataFrame([{"3M": 4.5, "10Y": 4.4}])


def test_finish_attaches_resolved_charts(tmp_path, monkeypatch):
    import castelino.agents.research.deep.chart_resolver as cr
    monkeypatch.setattr(cr, "get_adapter", lambda: _FakeAdapter())

    llm = _llm_with_chart()
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(
        llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("anything")
    sess = orch.run_first_round(sess.id, answers={})
    sess = orch.finish(sess.id)

    assert sess.status == ResearchStatus.COMPLETE
    assert len(sess.report.charts) == 1
    assert sess.report.charts[0].type == "yield_curve"
    assert sess.report.charts[0].series[0].points  # has real (fake) data


def test_finish_chart_failure_keeps_report_complete(tmp_path, monkeypatch):
    import castelino.agents.research.deep.chart_resolver as cr

    class _Boom:
        def yield_curve(self):
            raise RuntimeError("openbb down")

    monkeypatch.setattr(cr, "get_adapter", lambda: _Boom())

    llm = _llm_with_chart()
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(
        llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("anything")
    sess = orch.run_first_round(sess.id, answers={})
    sess = orch.finish(sess.id)

    assert sess.status == ResearchStatus.COMPLETE  # report NOT failed
    assert sess.report.charts == []  # chart dropped
