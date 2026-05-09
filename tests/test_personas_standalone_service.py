import json
from datetime import datetime, UTC, timedelta

import pytest
import yaml

from castelino.agents.base import FakeLLMClient
from castelino.agents.personas.agent import PersonaResponse
from castelino.agents.personas.models import (
    PersonaCard, PersonaMessage, PersonaStandaloneThread,
)


@pytest.fixture
def fixture_persona_root(tmp_path):
    pytest.importorskip("chromadb")
    card = PersonaCard(
        persona_id="krugman", full_name="Paul Krugman",
        role="Keynesian economist", tenure="",
        belief_summary="austerity politics, zombie ideas",
        decision_framework=[], signature_phrases=[],
        famous_calls=[], voice_notes="",
    )
    p = tmp_path / "agents" / "krugman" / "profile.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(json.loads(card.model_dump_json())))
    return tmp_path


def test_send_persists_thread_and_returns_assistant_msg(
    fixture_persona_root, monkeypatch,
):
    from castelino.agents.personas.standalone import PersonaStandaloneService

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="ok", cited_sources=[]))
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )

    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    msg = svc.send(persona_id="krugman", user_text="What about stagflation?")
    assert msg.role == "assistant"
    assert msg.text == "ok"

    thread = svc.load_thread(persona_id="krugman")
    assert thread.persona_id == "krugman"
    assert len(thread.messages) == 2
    assert thread.messages[0].role == "user"
    assert thread.messages[1].role == "assistant"


def test_send_reuses_existing_thread(fixture_persona_root, monkeypatch):
    from castelino.agents.personas.standalone import PersonaStandaloneService

    fake = FakeLLMClient()
    fake.register("PersonaResponse",
                  lambda s, u: PersonaResponse(text="ok", cited_sources=[]))
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )

    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    svc.send(persona_id="krugman", user_text="Q1")
    svc.send(persona_id="krugman", user_text="Q2")

    thread = svc.load_thread(persona_id="krugman")
    assert len(thread.messages) == 4
    user_msgs = [m for m in thread.messages if m.role == "user"]
    assert [m.text for m in user_msgs] == ["Q1", "Q2"]


def test_send_filters_old_messages_from_llm_context(
    fixture_persona_root, monkeypatch,
):
    """Messages older than 30 days stay on disk but don't go to the LLM."""
    from castelino.agents.personas.standalone import PersonaStandaloneService

    captured_user_prompt = {"text": ""}

    def _handler(system, user):
        captured_user_prompt["text"] = user
        return PersonaResponse(text="r", cited_sources=[])

    fake = FakeLLMClient()
    fake.register("PersonaResponse", _handler)
    monkeypatch.setattr(
        "castelino.agents.personas.store.PersonaStore._embed",
        lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts],
    )

    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    ancient = datetime.now(UTC) - timedelta(days=60)
    recent = datetime.now(UTC) - timedelta(days=1)
    pre_thread = PersonaStandaloneThread(
        persona_id="krugman",
        started_at=ancient,
        last_active_at=recent,
        messages=[
            PersonaMessage(role="user", text="ANCIENT_TEXT_AAA",
                           timestamp=ancient),
            PersonaMessage(role="user", text="RECENT_TEXT_BBB",
                           timestamp=recent),
        ],
    )
    path = svc._thread_path("krugman")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pre_thread.model_dump_json())

    svc.send(persona_id="krugman", user_text="now")

    assert "RECENT_TEXT_BBB" in captured_user_prompt["text"]
    assert "ANCIENT_TEXT_AAA" not in captured_user_prompt["text"]

    thread = svc.load_thread(persona_id="krugman")
    user_texts = [m.text for m in thread.messages if m.role == "user"]
    assert "ANCIENT_TEXT_AAA" in user_texts
    assert "RECENT_TEXT_BBB" in user_texts
    assert "now" in user_texts


def test_load_thread_returns_empty_when_no_file(fixture_persona_root):
    from castelino.agents.personas.standalone import PersonaStandaloneService

    fake = FakeLLMClient()
    svc = PersonaStandaloneService(
        client=fake, data_root=fixture_persona_root, in_memory_store=True,
    )
    thread = svc.load_thread(persona_id="krugman")
    assert thread.persona_id == "krugman"
    assert thread.messages == []
