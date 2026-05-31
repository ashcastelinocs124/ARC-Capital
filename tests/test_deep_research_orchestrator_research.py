import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    ClarifierResult,
    DecompositionResult,
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


def _llm_with(n_subs):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Q?", clarifying_questions=[]))
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id=f"q{i}", text=f"sub {i}") for i in range(n_subs)]
    ))
    llm.register("SubFinding", lambda s, u: SubFinding(
        sub_question_id="x", summary="found", key_points=["k"], confidence=0.7,
    ))
    return llm


def test_research_fans_out_and_caps_budget(tmp_path):
    llm = _llm_with(n_subs=10)        # tries 10
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    # capped to max_sub_questions (6) → 6 sonar calls, not 10
    assert sonar.call_count == 6
    assert len(sess.rounds[0].findings) == 6
    assert sess.status == ResearchStatus.SYNTHESIZING
