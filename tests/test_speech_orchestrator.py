"""Tests for the speech listener orchestrator.

Drives the full bridge end-to-end with a FakeSTTProvider (canned segments),
a FakeLLMClient (canned hawkish-shift verdict), and a fixture persona.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from castelino.agents.base import FakeLLMClient
from castelino.triggers.calendar import CalendarEvent
from castelino.triggers.figure_deviation.events import SpeechEventRecord
from castelino.triggers.figure_deviation.llm_gate import SpeechShiftClassification
from castelino.triggers.figure_deviation.speech_models import (
    BaselineVector, SpeakerPersona,
)
from castelino.triggers.figure_deviation.orchestrator import (
    event_id_for,
    run_listener_for_event,
    should_spawn_listener,
    _active_listeners,
)
from castelino.triggers.figure_deviation.persona import save_persona
from castelino.triggers.figure_deviation.queue import speech_trigger_queue
from castelino.triggers.figure_deviation.stt import FakeSTTProvider, TranscriptEvent


def _fixture_event(*, in_minutes: int = 2, has_live: bool = True, speaker_id: str | None = "powell") -> CalendarEvent:
    return CalendarEvent(
        name="FOMC Press Conference",
        timestamp=datetime.now(UTC) + timedelta(minutes=in_minutes),
        region="US",
        impact="high",
        asset_classes_affected=["rates", "equities"],
        has_live_stream=has_live,
        speaker_id=speaker_id,
    )


@pytest.fixture
def powell_persona(tmp_path, monkeypatch):
    """Save a fixture Powell persona under a tmp data root."""
    persona = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair, Federal Reserve",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=-0.15,
            hawkish_dovish_std=0.20,
            key_phrase_frequencies={},
            hedging_density=0.18,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    save_persona(persona, root=tmp_path)
    # Patch _personas_dir so load_persona finds the fixture
    from castelino.triggers.figure_deviation import persona as persona_mod
    monkeypatch.setattr(persona_mod, "_personas_dir",
                        lambda root=None: tmp_path / "personas" if root is None else root / "personas")
    return persona


# ─────────────────────────── should_spawn_listener ──────────────────────


def test_should_spawn_listener_within_window():
    _active_listeners.clear()
    assert should_spawn_listener(_fixture_event(in_minutes=2)) is True


def test_should_spawn_listener_too_far_in_future_rejected():
    _active_listeners.clear()
    assert should_spawn_listener(_fixture_event(in_minutes=60)) is False


def test_should_spawn_listener_past_event_rejected():
    _active_listeners.clear()
    assert should_spawn_listener(_fixture_event(in_minutes=-10)) is False


def test_should_spawn_listener_no_live_stream_rejected():
    _active_listeners.clear()
    assert should_spawn_listener(_fixture_event(has_live=False)) is False


def test_should_spawn_listener_no_speaker_rejected():
    _active_listeners.clear()
    assert should_spawn_listener(_fixture_event(speaker_id=None)) is False


def test_should_spawn_listener_already_active_rejected():
    _active_listeners.clear()
    ev = _fixture_event(in_minutes=2)
    _active_listeners.add(event_id_for(ev))
    try:
        assert should_spawn_listener(ev) is False
    finally:
        _active_listeners.clear()


# ─────────────────────────── run_listener_for_event ─────────────────────


def test_run_listener_pipes_segments_through_emitter_to_queue(powell_persona, tmp_path):
    """End-to-end: STT events → emitter → trigger → speech_trigger_queue + record."""
    speech_trigger_queue.clear()

    # Canned STT stream — first half neutral/dovish, then a hawkish pivot
    canned = [
        TranscriptEvent(text="Today the Committee met.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="We will be patient.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Considerable progress has been made.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Further firming may be warranted.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Inflation persistent and elevated price pressures remain.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="We will act decisively.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Persistent inflation requires policy firming.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Remain restrictive.", timestamp=datetime.now(UTC), is_final=True),
    ]
    provider = FakeSTTProvider(canned=canned)

    fake_llm = FakeLLMClient()
    fake_llm.register(
        "SpeechShiftClassification",
        lambda system, user: SpeechShiftClassification(
            is_shift=True, direction="hawkish", magnitude=0.7,
            decisive_phrase="Further firming may be warranted.",
            rationale="Out-of-character for Powell baseline.",
        ),
    )

    event = _fixture_event(in_minutes=0)
    record = asyncio.run(
        run_listener_for_event(
            event,
            provider=provider,
            audio_url="fake://",
            llm_client=fake_llm,
            save_root=tmp_path,
        )
    )

    assert isinstance(record, SpeechEventRecord)
    assert record.speaker_id == "powell"
    assert len(record.scored_sentences) == len(canned)
    assert len(record.triggers_fired) == 1
    assert record.triggers_fired[0].source.value == "speech_deviation"

    # Trigger landed on the global queue
    drained = speech_trigger_queue.drain()
    assert len(drained) == 1
    assert drained[0].source.value == "speech_deviation"

    # Per-event record persisted to disk
    saved = (tmp_path / "speech_events" / f"{event_id_for(event)}.json")
    assert saved.exists()


def test_runner_tick_spawns_listener_for_qualifying_event(monkeypatch):
    """tick() should call _maybe_spawn_speech_listeners with calendar events."""
    from castelino.triggers import runner as r

    spawned: list = []

    def _fake_spawn(event, *, provider_factory, llm_client_factory, stream_resolver):
        spawned.append(event)
        return None

    # Replace the orchestrator function inside _maybe_spawn_speech_listeners
    import castelino.triggers.figure_deviation.orchestrator as orch
    monkeypatch.setattr(orch, "spawn_listener_threaded", _fake_spawn)

    ev = _fixture_event(in_minutes=2)
    monkeypatch.setattr(r.calmod, "events_due", lambda: [ev])
    monkeypatch.setattr(r, "fetch_recent", lambda **kw: [])
    monkeypatch.setattr(r, "_check_regime_shift", lambda s: None)
    monkeypatch.setattr(r, "_check_conviction", lambda lf: (None, []))
    monkeypatch.setattr(r, "_trigger_cron_fallback", lambda lf: None)
    monkeypatch.setattr(r, "_trigger_from_calendar", lambda evs: None)

    r.tick()
    assert len(spawned) == 1
    assert spawned[0].name == "FOMC Press Conference"


def test_run_listener_calm_speech_emits_no_triggers(powell_persona, tmp_path):
    speech_trigger_queue.clear()
    canned = [
        TranscriptEvent(text="Today the Committee met.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Hello, everyone.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Thanks for being here.", timestamp=datetime.now(UTC), is_final=True),
    ]
    provider = FakeSTTProvider(canned=canned)
    fake_llm = FakeLLMClient()
    fake_llm.register(
        "SpeechShiftClassification",
        lambda system, user: SpeechShiftClassification(
            is_shift=False, direction="neutral", magnitude=0.0,
            decisive_phrase="", rationale="baseline",
        ),
    )
    event = _fixture_event(in_minutes=0)
    record = asyncio.run(
        run_listener_for_event(
            event, provider=provider, audio_url="fake://",
            llm_client=fake_llm, save_root=tmp_path,
        )
    )
    assert len(record.triggers_fired) == 0
    assert speech_trigger_queue.drain() == []
