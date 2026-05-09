"""Auto-start the speech listener for scheduled calendar events.

Bridges the live listener to the rest of the pipeline:
- decides whether to spawn for an upcoming event (`should_spawn_listener`)
- runs one full STT session and feeds the deviation emitter
  (`run_listener_for_event`)
- pushes any emitted TriggerRecords onto the global speech queue so
  `runner.tick()` picks them up
- persists a per-event SpeechEventRecord at the end

`spawn_listener_threaded` is the synchronous entry point used by
`runner.tick()` — fires off a daemon thread with its own asyncio loop
so the watch loop can return immediately.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from castelino.config import get_settings
from castelino.triggers.calendar import CalendarEvent
from castelino.triggers.figure_deviation.emitter import SpeechTriggerEmitter
from castelino.triggers.figure_deviation.events import SpeechEventRecord, save_event_record
from castelino.triggers.figure_deviation.listener import listen
from castelino.triggers.figure_deviation.persona import load_persona
from castelino.triggers.figure_deviation.queue import speech_trigger_queue
from castelino.triggers.figure_deviation.scorer import (
    POLICY_RELEVANT_THRESHOLD, load_lexicon, score_sentence,
)
from castelino.triggers.figure_deviation.stt import SpeechToTextProvider

log = logging.getLogger(__name__)


# Process-local set of event_ids currently being listened to. Prevents the
# 15-minute tick from spawning duplicate listeners for the same event.
_active_listeners: set[str] = set()
_active_lock = threading.Lock()


def event_id_for(event: CalendarEvent) -> str:
    """Stable id derived from the event's date + name."""
    date_part = event.timestamp.strftime("%Y-%m-%d")
    name_slug = event.name.lower().replace(" ", "-")
    return f"{date_part}-{name_slug}"


def should_spawn_listener(
    event: CalendarEvent,
    *,
    lookahead_minutes: int = 5,
    now: datetime | None = None,
) -> bool:
    """True if a listener should be spawned for this event right now.

    Conditions: speech enabled, event flags has_live_stream, has a speaker_id,
    isn't already being listened to, and starts within `lookahead_minutes`
    (and isn't in the past).
    """
    cfg = get_settings()
    if not cfg.speech.enabled:
        return False
    if not event.has_live_stream:
        return False
    if not event.speaker_id:
        return False
    if event_id_for(event) in _active_listeners:
        return False
    n = now or datetime.now(UTC)
    delta = event.timestamp - n
    if delta < timedelta(0):
        return False
    if delta > timedelta(minutes=lookahead_minutes):
        return False
    return True


async def run_listener_for_event(
    event: CalendarEvent,
    *,
    provider: SpeechToTextProvider,
    audio_url: str,
    llm_client,
    save_root=None,
) -> SpeechEventRecord:
    """Run a complete listening session and return the saved record.

    Streams STT events → SpeechSegments → emitter → triggers onto the
    global queue. Always persists a SpeechEventRecord on exit, even on
    error, so the transcript survives partial sessions.
    """
    cfg = get_settings()
    eid = event_id_for(event)
    with _active_lock:
        _active_listeners.add(eid)

    persona = load_persona(event.speaker_id)
    emitter = SpeechTriggerEmitter(
        speaker_id=event.speaker_id,
        full_name=persona.full_name,
        baseline=persona.baseline_vector,
        threshold_sigma=cfg.speech.deviation_threshold_sigma,
        llm_client=llm_client,
        lexicon_version=cfg.speech.lexicon_version,
        window_size=cfg.speech.window_size,
    )
    lex = load_lexicon(cfg.speech.lexicon_version)
    record = SpeechEventRecord(
        event_id=eid,
        speaker_id=event.speaker_id,
        started_at=datetime.now(UTC),
    )

    try:
        async for seg in listen(
            provider=provider,
            audio_url=audio_url,
            speaker_id=event.speaker_id,
            event_id=eid,
        ):
            score = score_sentence(seg.text, lexicon=lex)
            record.scored_sentences.append((seg.text, score))
            before = len(emitter.triggers)
            emitter.ingest(seg)
            for trg in emitter.triggers[before:]:
                speech_trigger_queue.offer(trg)
                record.triggers_fired.append(trg)
    except Exception:
        log.exception("listener failed mid-session for %s", eid)
    finally:
        with _active_lock:
            _active_listeners.discard(eid)
        save_event_record(record, root=save_root)

    return record


def spawn_listener_threaded(
    event: CalendarEvent,
    *,
    provider_factory: Callable[[], SpeechToTextProvider],
    llm_client_factory: Callable[[], object],
    stream_resolver: Callable[[CalendarEvent], Awaitable[str | None]],
) -> threading.Thread | None:
    """Start a background thread that runs the async listener for one event.

    Returns the thread (already started) or None if spawn was rejected. The
    factories defer construction so the thread is the one that holds STT
    connections / LLM clients — keeps the watcher tick lightweight.
    """
    if not should_spawn_listener(event):
        return None

    eid = event_id_for(event)

    def _runner() -> None:
        async def _go():
            audio_url = await stream_resolver(event)
            if not audio_url:
                log.warning("no audio URL resolved for %s", event.name)
                return
            provider = provider_factory()
            llm_client = llm_client_factory()
            await run_listener_for_event(
                event,
                provider=provider,
                audio_url=audio_url,
                llm_client=llm_client,
            )

        try:
            asyncio.run(_go())
        except Exception:
            log.exception("listener thread crashed for %s", eid)

    t = threading.Thread(target=_runner, daemon=True, name=f"speech-listener-{eid}")
    t.start()
    log.info("spawned listener thread for %s", event.name)
    return t


# ────────────────────────── stream resolver dispatch table ──────────────
#
# Maps a lowercase keyword (matched against event.name and event.speaker_id)
# to an async resolver. Extend here to add speakers / venues — no if/elif
# chains needed. First matching key wins.


async def _resolve_fomc(event: CalendarEvent) -> str | None:
    import httpx
    from castelino.triggers.figure_deviation.streams import (
        FOMC_MONETARY_POLICY_PAGE, parse_fomc_live_url,
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(FOMC_MONETARY_POLICY_PAGE)
            r.raise_for_status()
            return parse_fomc_live_url(r.text)
    except Exception as e:
        log.warning("failed to resolve FOMC stream URL: %s", e)
        return None


async def _resolve_stub(event: CalendarEvent) -> str | None:
    log.info(
        "no live-stream source configured for %s (speaker=%s) — skipping STT",
        event.name, event.speaker_id,
    )
    return None


_STREAM_DISPATCH: dict[str, Callable[[CalendarEvent], Awaitable[str | None]]] = {
    "fomc": _resolve_fomc,
    "waller": _resolve_stub,   # Christopher Waller — no known stream source yet
    "barkin": _resolve_stub,   # Thomas Barkin — no known stream source yet
}


async def default_stream_resolver(event: CalendarEvent) -> str | None:
    """Config-driven dispatch: match event name / speaker_id against _STREAM_DISPATCH.

    Each entry in _STREAM_DISPATCH is a keyword checked as a substring of
    event.name (lowercased) and event.speaker_id (lowercased). Add new
    speakers by inserting a key → resolver pair — no code changes elsewhere.
    """
    name_lower = event.name.lower()
    speaker_lower = (event.speaker_id or "").lower()
    for key, resolver in _STREAM_DISPATCH.items():
        if key in name_lower or key in speaker_lower:
            return await resolver(event)
    log.info(
        "no stream resolver matched for %s (speaker=%s)",
        event.name, event.speaker_id,
    )
    return None


def default_provider_factory() -> SpeechToTextProvider:
    """Build the configured STT provider. Raises if env / SDK missing."""
    cfg = get_settings()
    if cfg.speech.stt_provider == "deepgram":
        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY env var not set")
        from castelino.triggers.figure_deviation.stt_deepgram import DeepgramSTTProvider

        return DeepgramSTTProvider(api_key=api_key, model=cfg.speech.deepgram_model)
    raise RuntimeError(f"Unknown STT provider: {cfg.speech.stt_provider}")


def default_llm_client_factory():
    """Build the OpenAI client used for Stage B confirmation."""
    from castelino.agents.base import OpenAIClient

    return OpenAIClient()
