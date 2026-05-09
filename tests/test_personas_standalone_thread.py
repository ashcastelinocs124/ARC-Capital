from datetime import datetime, UTC
from castelino.agents.personas.models import (
    PersonaMessage, PersonaStandaloneThread,
)


def test_thread_round_trips_json():
    t = PersonaStandaloneThread(
        persona_id="krugman",
        started_at=datetime(2026, 5, 1, tzinfo=UTC),
        last_active_at=datetime(2026, 5, 8, tzinfo=UTC),
        messages=[
            PersonaMessage(role="user", text="hi", timestamp=datetime.now(UTC)),
            PersonaMessage(role="assistant", text="hello", timestamp=datetime.now(UTC)),
        ],
    )
    raw = t.model_dump_json()
    loaded = PersonaStandaloneThread.model_validate_json(raw)
    assert loaded == t


def test_thread_default_empty_messages():
    t = PersonaStandaloneThread(
        persona_id="x",
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
    )
    assert t.messages == []
