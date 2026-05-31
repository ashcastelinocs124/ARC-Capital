import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    ClarifierResult,
    DecompositionResult,
    ResearchStatus,
    SubQuestion,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.store import ResearchStore


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_llm_client(None)


def test_all_subagents_fail_marks_failed(tmp_path):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Q?", clarifying_questions=[]))
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id="q0", text="a"), SubQuestion(id="q1", text="b")]))
    # SubFinding handler never invoked because Sonar returns empty (→ error finding)
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="", sources=[]))  # always empty
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    assert sess.status == ResearchStatus.FAILED
    assert sess.error is not None
