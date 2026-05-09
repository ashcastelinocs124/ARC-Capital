"""Tests for the config-driven _STREAM_DISPATCH table and default_stream_resolver."""
import asyncio
from datetime import UTC, datetime, timedelta

from castelino.triggers.calendar import CalendarEvent
from castelino.triggers.speech.orchestrator import (
    _STREAM_DISPATCH,
    default_stream_resolver,
)


def _event(name: str, speaker_id: str | None = None) -> CalendarEvent:
    return CalendarEvent(
        name=name,
        timestamp=datetime.now(UTC) + timedelta(hours=1),
        region="US",
        impact="high",
        asset_classes_affected=["rates"],
        has_live_stream=True,
        speaker_id=speaker_id,
    )


def test_dispatch_table_contains_expected_keys():
    assert "fomc" in _STREAM_DISPATCH
    assert "waller" in _STREAM_DISPATCH
    assert "barkin" in _STREAM_DISPATCH


def test_fomc_entry_is_callable():
    import asyncio
    import inspect
    resolver = _STREAM_DISPATCH["fomc"]
    assert callable(resolver)
    assert inspect.iscoroutinefunction(resolver)


def test_fomc_resolver_dispatched_via_event_name(monkeypatch):
    """FOMC keyword in event name routes to the FOMC resolver (stubbed)."""
    async def _fake_fomc(event):
        return "https://youtube.com/watch?v=fomc-live"

    monkeypatch.setitem(_STREAM_DISPATCH, "fomc", _fake_fomc)
    url = asyncio.run(default_stream_resolver(_event("FOMC Press Conference")))
    assert url == "https://youtube.com/watch?v=fomc-live"


def test_waller_returns_none_via_speaker_id():
    url = asyncio.run(default_stream_resolver(_event("Fed Remarks", speaker_id="waller")))
    assert url is None


def test_waller_returns_none_via_event_name():
    url = asyncio.run(default_stream_resolver(_event("Waller Speech on Inflation")))
    assert url is None


def test_barkin_returns_none_via_event_name():
    url = asyncio.run(default_stream_resolver(_event("Barkin Remarks on the Outlook")))
    assert url is None


def test_barkin_returns_none_via_speaker_id():
    url = asyncio.run(default_stream_resolver(_event("Fed Remarks", speaker_id="barkin")))
    assert url is None


def test_unknown_speaker_returns_none():
    url = asyncio.run(
        default_stream_resolver(_event("ECB Press Conference", speaker_id="lagarde"))
    )
    assert url is None


def test_case_insensitive_match():
    """Matching is case-insensitive on both name and speaker_id."""
    url = asyncio.run(default_stream_resolver(_event("WALLER REMARKS")))
    assert url is None  # stub resolver — just verifies routing doesn't raise
