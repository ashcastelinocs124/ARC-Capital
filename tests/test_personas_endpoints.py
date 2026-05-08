import json

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def stubbed_dashboard(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")

    from castelino.agents.base import FakeLLMClient
    from castelino.agents.personas.agent import PersonaResponse
    from castelino.agents.personas.models import PersonaCard
    from castelino.dashboard.main import app
    from castelino.orchestrator.approval import ApprovalQueue, GateType

    # Stub data dirs by patching ApprovalQueue + persona dirs
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_HYPOTHESIS,
                 payload={"thesis": "long XLE"}, entry_id="H-x")

    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="t", belief_summary="b",
        decision_framework=[], signature_phrases=[], famous_calls=[],
        voice_notes="v",
    )
    p = tmp_path / "agents" / "buffett" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="Hold.", cited_sources=[]))

    # Patch the queue + LLM client + persona data root used by endpoints
    monkeypatch.setattr("castelino.dashboard.endpoints.approvals.ApprovalQueue",
                        lambda *a, **kw: queue)
    monkeypatch.setattr("castelino.agents.base.get_llm_client",
                        lambda: fake)
    monkeypatch.setattr("castelino.dashboard.endpoints.personas._agents_dir",
                        lambda: tmp_path / "agents")
    monkeypatch.setattr("castelino.agents.personas.store.PersonaStore._embed",
                        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])

    return TestClient(app), queue, tmp_path


def test_send_message_endpoint(stubbed_dashboard):
    client, queue, _ = stubbed_dashboard
    r = client.post(
        "/approvals/H-x/conversations/buffett/messages",
        json={"text": "what do you think?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "assistant"
    assert "Hold" in body["text"]


def test_list_personas_endpoint(stubbed_dashboard):
    client, _, _ = stubbed_dashboard
    r = client.get("/personas")
    assert r.status_code == 200
    cards = r.json()
    assert any(c["persona_id"] == "buffett" for c in cards)


def test_get_persona_endpoint(stubbed_dashboard):
    client, _, _ = stubbed_dashboard
    r = client.get("/personas/buffett")
    assert r.status_code == 200
    assert r.json()["persona_id"] == "buffett"


def test_get_persona_not_found(stubbed_dashboard):
    client, _, _ = stubbed_dashboard
    r = client.get("/personas/not_real")
    assert r.status_code == 404
