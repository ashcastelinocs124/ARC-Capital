import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    ClarificationQuestion,
    ClarifierResult,
    ResearchStatus,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient
from castelino.agents.research.deep.store import ResearchStore


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_llm_client(None)


def _orch(tmp_path, llm, sonar=None):
    set_llm_client(llm)
    return DeepResearchOrchestrator(
        llm=llm, sonar=sonar or FakeSonarClient(),
        store=ResearchStore(root=tmp_path),
    )


def test_start_rewords_and_pauses(tmp_path):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Precise Q?",
        clarifying_questions=[ClarificationQuestion(question="Scope?")],
    ))
    orch = _orch(tmp_path, llm)
    sess = orch.start("raw query")
    assert sess.status == ResearchStatus.AWAITING_ANSWERS
    assert sess.reworded_query == "Precise Q?"
    assert len(sess.clarifying_questions) == 1
    # persisted
    assert orch.store.load(sess.id).status == ResearchStatus.AWAITING_ANSWERS


def test_start_no_questions_still_awaits(tmp_path):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Precise Q?", clarifying_questions=[],
    ))
    orch = _orch(tmp_path, llm)
    sess = orch.start("raw query")
    assert sess.status == ResearchStatus.AWAITING_ANSWERS
    assert sess.clarifying_questions == []
