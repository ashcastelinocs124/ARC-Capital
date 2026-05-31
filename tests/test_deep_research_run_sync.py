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


def test_run_sync_end_to_end(tmp_path):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(reworded_query="Q?", clarifying_questions=[]))
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id="q0", text="a")]))
    llm.register("SubFinding", lambda s, u: SubFinding(sub_question_id="q0", summary="f", confidence=0.8))
    llm.register("DeepResearchReport", lambda s, u: DeepResearchReport(exec_summary="done", confidence=0.8))
    llm.register("ReflectionResult", lambda s, u: ReflectionResult(is_sufficient=True))
    set_llm_client(llm)
    orch = DeepResearchOrchestrator(
        llm=llm, sonar=FakeSonarClient(default=SonarResult(content="x", sources=[])),
        store=ResearchStore(root=tmp_path))
    sess = orch.run_sync("research question", answers={})
    assert sess.status == ResearchStatus.COMPLETE
    assert sess.report.exec_summary == "done"
