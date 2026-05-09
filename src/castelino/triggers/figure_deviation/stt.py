"""SpeechToTextProvider interface + Fake implementation.

Real Deepgram impl lives in stt_deepgram.py (Task 14) — kept separate so
unit tests don't pull the SDK.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    timestamp: datetime
    is_final: bool


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def stream(self, *, audio_url: str) -> AsyncIterator[TranscriptEvent]:
        ...


class FakeSTTProvider(SpeechToTextProvider):
    """Yields a canned sequence — used by tests and dry-runs."""

    def __init__(self, canned: list[TranscriptEvent]):
        self._canned = list(canned)

    async def stream(self, *, audio_url: str) -> AsyncIterator[TranscriptEvent]:
        for ev in self._canned:
            yield ev
