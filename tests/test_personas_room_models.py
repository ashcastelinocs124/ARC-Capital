from datetime import datetime, UTC
from castelino.agents.personas.models import (
    Citation, RoomMessage, PersonaRoom,
)


def test_room_message_round_trips():
    m = RoomMessage(
        speaker="krugman", text="hello",
        timestamp=datetime.now(UTC), turn=1,
        citations=[Citation(source="x", snippet="y", score=0.5)],
    )
    assert RoomMessage.model_validate_json(m.model_dump_json()) == m


def test_room_message_user_speaker_no_citations():
    m = RoomMessage(speaker="user", text="hi", timestamp=datetime.now(UTC), turn=1)
    assert m.citations == []


def test_persona_room_round_trips():
    r = PersonaRoom(
        room_id="stagflation-q4",
        name="Stagflation Q4",
        member_persona_ids=["krugman", "dalio"],
        context="Stress-testing long energy",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        last_active_at=datetime(2026, 5, 9, tzinfo=UTC),
        messages=[RoomMessage(
            speaker="user", text="thoughts?", timestamp=datetime.now(UTC), turn=1,
        )],
    )
    assert PersonaRoom.model_validate_json(r.model_dump_json()) == r


def test_persona_room_defaults():
    r = PersonaRoom(
        room_id="x", name="X", member_persona_ids=["a"],
        created_at=datetime.now(UTC), last_active_at=datetime.now(UTC),
    )
    assert r.context == ""
    assert r.messages == []
