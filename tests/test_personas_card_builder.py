from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.card_builder import generate_profile_card
from castelino.agents.personas.corpus import CorpusChunk
from castelino.agents.personas.models import FamousCall, PersonaCard


def test_generate_profile_card_returns_typed_output():
    canned = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="hold quality companies forever",
        decision_framework=["margin of safety"],
        signature_phrases=["intrinsic value"],
        famous_calls=[FamousCall(date="2008", description="GS preferred")],
        voice_notes="folksy, anecdotal",
    )
    fake = FakeLLMClient()
    fake.register("PersonaCard", lambda system, user: canned)

    chunks = [CorpusChunk(id="x", text="quality companies", metadata={})]
    card = generate_profile_card(
        client=fake, persona_id="buffett",
        full_name="Warren Buffett", role="Value investor",
        sample_chunks=chunks,
    )
    assert card.persona_id == "buffett"
    assert "intrinsic value" in card.signature_phrases
    assert fake.stats.n_calls == 1


def test_generate_profile_card_passes_chunks_into_user_prompt():
    captured = {}
    fake = FakeLLMClient()
    def _handler(system, user):
        captured["user"] = user
        return PersonaCard(
            persona_id="x", full_name="x", role="r", tenure="",
            belief_summary="b", decision_framework=[],
            signature_phrases=[], famous_calls=[], voice_notes="",
        )
    fake.register("PersonaCard", _handler)
    chunks = [
        CorpusChunk(id="1", text="UNIQUE_PHRASE_AAA", metadata={}),
        CorpusChunk(id="2", text="UNIQUE_PHRASE_BBB", metadata={}),
    ]
    generate_profile_card(
        client=fake, persona_id="x", full_name="x", role="r",
        sample_chunks=chunks,
    )
    assert "UNIQUE_PHRASE_AAA" in captured["user"]
    assert "UNIQUE_PHRASE_BBB" in captured["user"]
