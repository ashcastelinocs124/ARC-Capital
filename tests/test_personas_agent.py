import json
from datetime import datetime, UTC
from pathlib import Path

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.corpus import CorpusChunk
from castelino.agents.personas.models import (
    PersonaCard, PersonaConversation, PersonaMessage,
)


@pytest.fixture
def card_on_disk(tmp_path):
    pytest.importorskip("chromadb")
    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="quality forever",
        decision_framework=["margin of safety"],
        signature_phrases=["intrinsic value"], famous_calls=[],
        voice_notes="folksy",
    )
    p = tmp_path / "agents" / "buffett" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return tmp_path


def test_persona_agent_chat_uses_retrieval_and_llm(card_on_disk, monkeypatch):
    from castelino.agents.personas.agent import PersonaAgent, PersonaResponse

    fake = FakeLLMClient()
    fake.register(
        "PersonaResponse",
        lambda s, u: PersonaResponse(text="Hold quality, full stop.",
                                     cited_sources=[]),
    )

    agent = PersonaAgent(
        persona_id="buffett", client=fake,
        data_root=card_on_disk, in_memory_store=True,
    )
    monkeypatch.setattr(agent.store, "_embed",
                        lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    agent.store.add_chunks([
        CorpusChunk(id="c1", text="quality companies",
                    metadata={"source": "1986.pdf", "url": "u"}),
    ])

    conversation = PersonaConversation(
        entry_id="H-1", persona_id="buffett",
        started_at=datetime.now(UTC), messages=[],
    )
    msg = agent.chat(conversation=conversation,
                     user_text="Should I buy this?",
                     approval_payload={"thesis": "long XLE on supply shock"})
    assert msg.role == "assistant"
    assert msg.text.startswith("Hold quality")
    assert fake.stats.n_calls == 1
    # Conversation has both user and assistant
    assert len(conversation.messages) == 2


def test_persona_agent_maps_cited_sources_to_citations(card_on_disk, monkeypatch):
    from castelino.agents.personas.agent import PersonaAgent, PersonaResponse

    fake = FakeLLMClient()
    fake.register(
        "PersonaResponse",
        lambda s, u: PersonaResponse(
            text="Per my 1986 letter, quality matters.",
            cited_sources=["1986.pdf"],
        ),
    )

    agent = PersonaAgent(
        persona_id="buffett", client=fake,
        data_root=card_on_disk, in_memory_store=True,
    )
    monkeypatch.setattr(agent.store, "_embed",
                        lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    agent.store.add_chunks([
        CorpusChunk(id="c1", text="quality companies",
                    metadata={"source": "1986.pdf", "url": "u"}),
    ])

    conv = PersonaConversation(
        entry_id="H-1", persona_id="buffett",
        started_at=datetime.now(UTC), messages=[],
    )
    msg = agent.chat(conversation=conv,
                     user_text="What's your view?",
                     approval_payload={"thesis": "x"})
    assert len(msg.citations) == 1
    assert msg.citations[0].source == "1986.pdf"
