from datetime import UTC, datetime

from castelino.triggers.calendar import CalendarEvent


def test_calendar_event_supports_speech_fields():
    e = CalendarEvent(
        name="FOMC Press Conference",
        timestamp=datetime.now(UTC),
        region="US",
        impact="high",
        asset_classes_affected=["rates", "equities"],
        has_live_stream=True,
        speaker_id="powell",
    )
    assert e.has_live_stream is True
    assert e.speaker_id == "powell"


def test_calendar_event_defaults_preserve_compatibility():
    e = CalendarEvent(
        name="x",
        timestamp=datetime.now(UTC),
        region="US",
        impact="low",
        asset_classes_affected=[],
    )
    assert e.has_live_stream is False
    assert e.speaker_id is None
