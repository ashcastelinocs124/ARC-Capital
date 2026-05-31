from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.lead import LeadAgent
from castelino.agents.research.deep.models import DecompositionResult, SubQuestion


def test_lead_decomposes_and_caps():
    fake = FakeLLMClient()
    # LLM tries to return 8; agent must cap to config max (6)
    fake.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id=f"q{i}", text=f"sub {i}") for i in range(8)]
    ))
    set_llm_client(fake)
    try:
        out = LeadAgent().decompose(
            reworded_query="Will the Fed cut in 2026?",
            answers={"Which meeting?": "all of 2026"},
            round_num=1,
        )
        assert len(out) <= 6
        assert all(isinstance(q, SubQuestion) for q in out)
    finally:
        set_llm_client(None)
