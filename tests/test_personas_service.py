import json
from datetime import datetime, UTC

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.models import PersonaCard
from castelino.orchestrator.approval import ApprovalQueue, GateType


@pytest.fixture
def queue_with_pending_item(tmp_path):
    pytest.importorskip("chromadb")
    q = ApprovalQueue(state_dir=tmp_path)
    q.submit(gate=GateType.POST_HYPOTHESIS,
             payload={"thesis": "long XLE supply shock"},
             entry_id="H-test")

    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="quality forever",
        decision_framework=["margin of safety"],
        signature_phrases=[], famous_calls=[], voice_notes="folksy",
    )
    p = tmp_path / "agents" / "buffett" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return q, tmp_path


def test_chat_service_appends_to_approval_item(queue_with_pending_item, monkeypatch):
    queue, data_root = queue_with_pending_item
    from castelino.agents.personas.agent import PersonaResponse
    from castelino.agents.personas.service import PersonaChatService

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="Hold quality.",
                                               cited_sources=[]))

    svc = PersonaChatService(
        queue=queue, client=fake,
        data_root=data_root, in_memory_store=True,
    )
    monkeypatch.setattr("castelino.agents.personas.store.PersonaStore._embed",
                        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])

    msg = svc.send(entry_id="H-test", persona_id="buffett",
                   user_text="What do you think?")
    assert msg.text == "Hold quality."

    item = queue.get("H-test")
    assert len(item.conversations) == 1
    conv = item.conversations[0]
    assert conv.persona_id == "buffett"
    assert len(conv.messages) == 2  # user + assistant


def test_chat_service_reuses_existing_conversation(queue_with_pending_item, monkeypatch):
    queue, data_root = queue_with_pending_item
    from castelino.agents.personas.agent import PersonaResponse
    from castelino.agents.personas.service import PersonaChatService

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="ok", cited_sources=[]))

    svc = PersonaChatService(
        queue=queue, client=fake,
        data_root=data_root, in_memory_store=True,
    )
    monkeypatch.setattr("castelino.agents.personas.store.PersonaStore._embed",
                        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])

    svc.send(entry_id="H-test", persona_id="buffett", user_text="Q1")
    svc.send(entry_id="H-test", persona_id="buffett", user_text="Q2")

    item = queue.get("H-test")
    # Still ONE conversation, not two
    assert len(item.conversations) == 1
    assert len(item.conversations[0].messages) == 4  # 2 user + 2 assistant
