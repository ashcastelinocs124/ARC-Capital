"""Deepgram streaming provider. Live audio -> TranscriptEvent stream.

Kept separate from `stt.py` so unit tests don't need to pull the Deepgram SDK.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

try:
    from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
except ImportError:  # pragma: no cover - exercised when SDK absent
    DeepgramClient = None  # type: ignore[assignment]
    LiveTranscriptionEvents = None  # type: ignore[assignment]
    LiveOptions = None  # type: ignore[assignment]

from castelino.triggers.figure_deviation.stt import SpeechToTextProvider, TranscriptEvent


class DeepgramSTTProvider(SpeechToTextProvider):
    """Streaming STT provider backed by Deepgram's `asynclive` API.

    The stream() coroutine yields `TranscriptEvent`s as the Deepgram
    websocket pushes transcription results. Final and interim results
    are surfaced — downstream consumers can filter on `is_final`.
    """

    def __init__(self, *, api_key: str, model: str = "nova-2-finance"):
        if DeepgramClient is None:
            raise RuntimeError(
                "deepgram-sdk not installed - add 'deepgram-sdk>=3,<4' to dependencies"
            )
        self.model = model
        self._api_key = api_key
        self._client = DeepgramClient(api_key)

    async def stream(self, *, audio_url: str) -> AsyncIterator[TranscriptEvent]:
        connection = self._client.listen.asynclive.v("1")
        queue: asyncio.Queue[TranscriptEvent] = asyncio.Queue()

        async def on_transcript(_self, result, **_kwargs):  # noqa: ANN001
            try:
                txt = result.channel.alternatives[0].transcript
            except (AttributeError, IndexError):
                return
            if not txt:
                return
            await queue.put(
                TranscriptEvent(
                    text=txt,
                    timestamp=datetime.now(UTC),
                    is_final=getattr(result, "is_final", True),
                )
            )

        connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
        await connection.start(LiveOptions(model=self.model, smart_format=True))
        try:
            while True:
                ev = await queue.get()
                yield ev
        finally:
            await connection.finish()
