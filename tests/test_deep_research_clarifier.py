from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.clarifier import ClarifierAgent
from castelino.agents.research.deep.models import (
    ClarificationQuestion,
    ClarifierResult,
)


def test_clarifier_rewords_and_asks():
    fake = FakeLLMClient()
    fake.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="What is the probability the Fed cuts rates in 2026?",
        clarifying_questions=[
            ClarificationQuestion(question="Which meeting?", why="timing matters"),
        ],
    ))
    set_llm_client(fake)
    try:
        out = ClarifierAgent()(query="will the fed cut")
        assert "Fed" in out.reworded_query
        assert len(out.clarifying_questions) == 1
    finally:
        set_llm_client(None)  # reset singleton
