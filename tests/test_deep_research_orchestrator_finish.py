import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
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


def _base_llm():
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Q?", clarifying_questions=[]))
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id="q0", text="sub 0")]))
    llm.register("SubFinding", lambda s, u: SubFinding(
        sub_question_id="q0", summary="f", confidence=0.7))
    llm.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="answer", confidence=0.7))
    return llm


def test_finish_sufficient_completes(tmp_path):
    llm = _base_llm()
    llm.register("ReflectionResult", lambda s, u: ReflectionResult(is_sufficient=True))
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    sess = orch.finish(sess.id)
    assert sess.status == ResearchStatus.COMPLETE
    assert sess.report.exec_summary == "answer"
    assert len(sess.rounds) == 1  # no extra round needed


def test_finish_insufficient_runs_second_round_then_stops(tmp_path):
    llm = _base_llm()
    # First reflection says insufficient with a gap; the loop is capped at max_rounds=2
    calls = {"n": 0}

    def _reflect(s, u):
        calls["n"] += 1
        if calls["n"] == 1:
            return ReflectionResult(
                is_sufficient=False, gaps=["missing X"],
                new_sub_questions=[SubQuestion(id="q1", text="X?")])
        return ReflectionResult(is_sufficient=True)

    llm.register("ReflectionResult", _reflect)
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    sess = orch.finish(sess.id)
    assert sess.status == ResearchStatus.COMPLETE
    assert len(sess.rounds) == 2  # one reflection-driven extra round, then capped
