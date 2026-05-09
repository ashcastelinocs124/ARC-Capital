import json

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def stubbed(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from castelino.agents.base import FakeLLMClient
    from castelino.agents.personas.agent import PersonaResponse
    from castelino.agents.personas.models import PersonaCard
    from castelino.dashboard.main import app

    for pid, name in [("krugman", "Paul Krugman"), ("dalio", "Ray Dalio")]:
        card = PersonaCard(
            persona_id=pid, full_name=name, role="r", tenure="",
            belief_summary="b", decision_framework=[], signature_phrases=[],
            famous_calls=[], voice_notes="",
        )
        p = tmp_path / "agents" / pid / "profile.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="reply", cited_sources=[]))

    from castelino.agents.personas.rooms import RoomService
    monkeypatch.setattr(
        "castelino.dashboard.endpoints.personas._room_service",
        lambda: RoomService(client=fake, data_root=tmp_path, in_memory_store=True),
    )
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )
    return TestClient(app)


def test_list_rooms_empty_initially(stubbed):
    r = stubbed.get("/rooms")
    assert r.status_code == 200
    assert r.json() == []


def test_create_then_list(stubbed):
    r = stubbed.post("/rooms", json={
        "name": "Stagflation Q4",
        "member_persona_ids": ["krugman", "dalio"],
        "context": "long energy",
    })
    assert r.status_code == 200
    assert r.json()["room_id"] == "stagflation-q4"
    r2 = stubbed.get("/rooms")
    assert len(r2.json()) == 1
    assert r2.json()[0]["name"] == "Stagflation Q4"


def test_get_room_returns_full_thread(stubbed):
    stubbed.post("/rooms", json={
        "name": "Test", "member_persona_ids": ["krugman"], "context": "",
    })
    r = stubbed.get("/rooms/test")
    assert r.status_code == 200
    assert r.json()["room_id"] == "test"
    assert r.json()["messages"] == []


def test_post_message_streams_ndjson(stubbed):
    stubbed.post("/rooms", json={
        "name": "Test", "member_persona_ids": ["krugman", "dalio"], "context": "",
    })
    with stubbed.stream(
        "POST", "/rooms/test/messages",
        json={"text": "thoughts?"},
    ) as resp:
        assert resp.status_code == 200
        lines = []
        for chunk in resp.iter_text():
            for line in chunk.split("\n"):
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
    speakers = [m["speaker"] for m in lines]
    assert speakers == ["user", "krugman", "dalio"]


def test_delete_room(stubbed):
    stubbed.post("/rooms", json={
        "name": "Doomed", "member_persona_ids": ["krugman"], "context": "",
    })
    r = stubbed.delete("/rooms/doomed")
    assert r.status_code in (200, 204)
    assert stubbed.get("/rooms").json() == []
