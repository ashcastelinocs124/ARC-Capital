from datetime import UTC, datetime

from castelino.agents.personas.models import (
    PanelDiscussion,
    PanelSynthesis,
    PersonaConversation,
    PersonaMessage,
)
from castelino.orchestrator.approval import ApprovalItem, GateType


def test_approval_item_has_conversations_default_empty():
    item = ApprovalItem(entry_id="H-1", gate=GateType.POST_HYPOTHESIS)
    assert item.conversations == []
    assert item.panel_discussions == []


def test_approval_item_round_trips_with_conversation():
    conv = PersonaConversation(
        entry_id="H-1",
        persona_id="buffett",
        started_at=datetime.now(UTC),
        messages=[PersonaMessage(role="user", text="hi", timestamp=datetime.now(UTC))],
    )
    item = ApprovalItem(
        entry_id="H-1",
        gate=GateType.POST_HYPOTHESIS,
        conversations=[conv],
    )
    raw = item.model_dump_json()
    loaded = ApprovalItem.model_validate_json(raw)
    assert len(loaded.conversations) == 1
    assert loaded.conversations[0].persona_id == "buffett"
