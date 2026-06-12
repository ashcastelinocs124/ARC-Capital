"""Tests for /discuss persona slash command."""
import castelino.agents.chat.registry as reg
from castelino.agents.chat.models import CommandName


def test_discuss_in_registry():
    assert CommandName.discuss in reg.REGISTRY
    spec = reg.REGISTRY[CommandName.discuss]
    assert spec.mutating is False
    assert "query" in spec.required_args


def test_discuss_list_shows_personas():
    result = reg._discuss({"query": "list"})
    for pid in ["krugman", "elerian", "summers", "druckenmiller", "dalio", "tudor_jones"]:
        assert pid in result.lower()


def test_discuss_unknown_persona():
    result = reg._discuss({"query": "buffett what about markets?"})
    assert "unknown" in result.lower()


def test_discuss_one_shot(monkeypatch):
    fake = type("Fake", (), {
        "chat": lambda self, **kw: type("Msg", (), {
            "text": "Dalio says: be cautious about leverage.", "cited_sources": [],
        })(),
    })()
    monkeypatch.setattr("castelino.agents.chat.registry.PersonaAgent", lambda **kw: fake)
    result = reg._discuss({"query": "dalio what about stagflation?"})
    assert "cautious" in result


def test_discuss_no_question_enters_multi_turn():
    reg._clear_pending_discuss()
    result = reg._discuss({"query": "dalio"})
    assert "dalio" in result.lower()
    assert reg._discuss_pending_persona == "dalio"
    reg._clear_pending_discuss()


def test_clear_pending_discuss():
    reg._discuss_pending_persona = "dalio"
    reg._clear_pending_discuss()
    assert reg._discuss_pending_persona is None


def test_discuss_panel(monkeypatch):
    calls = []
    class FakeAgent:
        def __init__(self, persona_id, **kw):
            self.persona_id = persona_id
        def chat(self, conversation, user_text, approval_payload):
            calls.append(self.persona_id)
            return type("Msg", (), {
                "text": f"{self.persona_id} says: analysis", "cited_sources": [],
            })()
    monkeypatch.setattr("castelino.agents.chat.registry.PersonaAgent", FakeAgent)
    result = reg._discuss({"query": "panel stagflation risk"})
    assert len(calls) == 6
    assert "analysis" in result.lower()


def test_handle_discuss_message(monkeypatch):
    reg._discuss_pending_persona = "dalio"
    from castelino.agents.personas.models import PersonaConversation
    from datetime import datetime, timezone
    reg._discuss_pending_conv = PersonaConversation(
        entry_id="test", persona_id="dalio",
        started_at=datetime.now(timezone.utc),
    )
    fake = type("Fake", (), {
        "chat": lambda self, **kw: type("Msg", (), {
            "text": "Dalio replies: diversify.", "cited_sources": [],
        })(),
    })()
    monkeypatch.setattr("castelino.agents.chat.registry.PersonaAgent", lambda **kw: fake)
    result = reg._handle_discuss_message("what's your view?")
    assert "diversify" in result
    reg._clear_pending_discuss()
