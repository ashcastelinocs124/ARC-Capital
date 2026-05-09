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

    card = PersonaCard(
        persona_id="krugman", full_name="Paul Krugman",
        role="Keynesian economist", tenure="",
        belief_summary="b", decision_framework=[], signature_phrases=[],
        famous_calls=[], voice_notes="",
    )
    p = tmp_path / "agents" / "krugman" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="standalone-ok",
                                               cited_sources=[]))

    monkeypatch.setattr(
        "castelino.dashboard.endpoints.personas.get_llm_client", lambda: fake,
    )
    monkeypatch.setattr(
        "castelino.dashboard.endpoints.personas._agents_dir",
        lambda: tmp_path / "agents",
    )
    monkeypatch.setattr(
        "castelino.dashboard.endpoints.personas._data_root",
        lambda: tmp_path,
    )
    # Override the standalone-service factory to use in-memory Chroma
    # (avoids colliding with any production collection on disk).
    from castelino.agents.personas.standalone import PersonaStandaloneService
    monkeypatch.setattr(
        "castelino.dashboard.endpoints.personas._standalone_service",
        lambda: PersonaStandaloneService(
            client=fake, data_root=tmp_path, in_memory_store=True,
        ),
    )
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )
    return TestClient(app), tmp_path


def test_get_thread_returns_empty_when_no_history(stubbed_dashboard):
    client, _ = stubbed_dashboard
    r = client.get("/personas/krugman/thread")
    assert r.status_code == 200
    body = r.json()
    assert body["persona_id"] == "krugman"
    assert body["messages"] == []


def test_send_message_appends_to_thread(stubbed_dashboard):
    client, _ = stubbed_dashboard
    r = client.post(
        "/personas/krugman/thread/messages",
        json={"text": "thoughts on stagflation?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "assistant"
    assert body["text"] == "standalone-ok"

    r2 = client.get("/personas/krugman/thread")
    assert len(r2.json()["messages"]) == 2
