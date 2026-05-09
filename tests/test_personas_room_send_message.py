import json
from datetime import datetime, timedelta, UTC

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.agent import PersonaResponse
from castelino.agents.personas.models import PersonaCard
from castelino.agents.personas.rooms import RoomService


@pytest.fixture
def two_personas_root(tmp_path):
    pytest.importorskip("chromadb")
    for pid, name in [("krugman", "Paul Krugman"), ("dalio", "Ray Dalio")]:
        card = PersonaCard(
            persona_id=pid, full_name=name, role="r", tenure="",
            belief_summary="b", decision_framework=[], signature_phrases=[],
            famous_calls=[], voice_notes="",
        )
        p = tmp_path / "agents" / pid / "profile.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return tmp_path


def test_send_message_round_robin_in_order(two_personas_root, monkeypatch):
    n = {"i": 0}
    def _handler(system, user):
        n["i"] += 1
        return PersonaResponse(text=f"reply-{n['i']}", cited_sources=[])
    fake = FakeLLMClient()
    fake.register("PersonaResponse", _handler)
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )
    svc = RoomService(client=fake, data_root=two_personas_root, in_memory_store=True)
    room = svc.create_room(
        name="Test", member_persona_ids=["krugman", "dalio"], context="",
    )
    replies = list(svc.send_message(room_id=room.room_id, user_text="thoughts?"))
    assert len(replies) == 3
    assert replies[0]["speaker"] == "user"
    assert replies[1]["speaker"] == "krugman"
    assert replies[1]["text"] == "reply-1"
    assert replies[2]["speaker"] == "dalio"
    assert replies[2]["text"] == "reply-2"
    saved = svc.load_room(room.room_id)
    assert len(saved.messages) == 3
    assert all(m.turn == 1 for m in saved.messages)


def test_persona_2_sees_persona_1_reply(two_personas_root, monkeypatch):
    captured = {"krugman_user_prompt": None, "dalio_user_prompt": None}
    n = {"i": 0}
    def _handler(system, user):
        n["i"] += 1
        if n["i"] == 1:
            captured["krugman_user_prompt"] = user
            return PersonaResponse(text="KRUGMAN_UNIQUE_TOKEN_AAA", cited_sources=[])
        captured["dalio_user_prompt"] = user
        return PersonaResponse(text="dalio reply", cited_sources=[])
    fake = FakeLLMClient()
    fake.register("PersonaResponse", _handler)
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )
    svc = RoomService(client=fake, data_root=two_personas_root, in_memory_store=True)
    room = svc.create_room(name="Test", member_persona_ids=["krugman", "dalio"], context="")
    list(svc.send_message(room_id=room.room_id, user_text="kick off"))
    assert "KRUGMAN_UNIQUE_TOKEN_AAA" in captured["dalio_user_prompt"]
    assert "dalio reply" not in captured["krugman_user_prompt"]


def test_skips_missing_persona(two_personas_root, monkeypatch):
    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="ok", cited_sources=[]))
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )
    svc = RoomService(client=fake, data_root=two_personas_root, in_memory_store=True)
    room = svc.create_room(
        name="Mixed", member_persona_ids=["krugman", "ghost"], context="",
    )
    replies = list(svc.send_message(room_id=room.room_id, user_text="hi"))
    persona_replies = [r for r in replies if r["speaker"] != "user"]
    assert len(persona_replies) == 1
    assert persona_replies[0]["speaker"] == "krugman"


def test_30_day_window_excludes_old(two_personas_root, monkeypatch):
    captured = {"prompt": ""}
    fake = FakeLLMClient()
    def _handler(system, user):
        captured["prompt"] = user
        return PersonaResponse(text="ok", cited_sources=[])
    fake.register("PersonaResponse", _handler)
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )
    svc = RoomService(client=fake, data_root=two_personas_root, in_memory_store=True)
    room = svc.create_room(name="Old", member_persona_ids=["krugman"], context="")
    from castelino.agents.personas.models import RoomMessage
    ancient = datetime.now(UTC) - timedelta(days=60)
    room.messages.append(RoomMessage(
        speaker="user", text="ANCIENT_AAA", timestamp=ancient, turn=1,
    ))
    svc._save(room)
    list(svc.send_message(room_id=room.room_id, user_text="now"))
    assert "ANCIENT_AAA" not in captured["prompt"]
