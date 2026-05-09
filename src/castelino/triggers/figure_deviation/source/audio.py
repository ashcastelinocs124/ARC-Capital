"""Audio source for the figure-deviation engine.

Adapts the existing Deepgram STT → SpeechSegment pipeline (see
`triggers/figure_deviation/listener.py` and `stt_deepgram.py`) into the
generic `FigurePost` shape, so the audio path becomes one implementation of
`FigurePostSource` alongside the X API and Sonar tweet sources.

Wave 2 wraps the existing audio path without rewriting it. The audio code in
`listener.py` and `stt*.py` remains untouched; this module is a thin adapter
layer that lets the orchestrator treat it as just-another-source.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from castelino.triggers.figure_deviation.listener import listen
from castelino.triggers.figure_deviation.models import FigurePost
from castelino.triggers.figure_deviation.source.base import FigurePostSource
from castelino.triggers.figure_deviation.speech_models import SpeechSegment
from castelino.triggers.figure_deviation.stt import SpeechToTextProvider


class AudioFigurePostSource(FigurePostSource):
    """Wraps the live audio listener as a `FigurePostSource`.

    Construction takes an STT provider and an audio URL resolver; `stream()`
    yields one `FigurePost` per transcribed sentence.
    """

    def __init__(
        self,
        provider: SpeechToTextProvider,
        audio_url: str,
        speaker_id: str,
        event_id: str,
    ) -> None:
        self._provider = provider
        self._audio_url = audio_url
        self._speaker_id = speaker_id
        self._event_id = event_id

    @staticmethod
    def adapt_segment(seg: SpeechSegment) -> FigurePost:
        """Convert one `SpeechSegment` to its generic `FigurePost` equivalent.

        The `figure_id` is taken from the segment's `speaker_id` — they are
        the same identifier under different names.
        """
        return FigurePost(
            figure_id=seg.speaker_id,
            text=seg.text,
            ts=seg.timestamp,
            source="audio",
            event_id=seg.event_id,
        )

    @classmethod
    async def from_segment_stream(
        cls, segments: AsyncIterator[SpeechSegment],
    ) -> AsyncIterator[FigurePost]:
        """Adapter for tests + alternative entry points: turn any
        `SpeechSegment` async iterator into a `FigurePost` async iterator.

        Useful for unit tests that synthesise segments directly without
        running the live audio pipeline.
        """
        async for seg in segments:
            yield cls.adapt_segment(seg)

    async def stream(self, figure, source_cfg) -> AsyncIterator[FigurePost]:
        """Yield `FigurePost`s from the live audio stream for this figure.

        `figure` and `source_cfg` are accepted for `FigurePostSource`
        compatibility but the existing audio listener does not yet read them
        directly — the speaker_id / event_id / audio_url were captured at
        construction time. Wave 5 generalises this when the orchestrator
        starts driving multi-figure polling.
        """
        async for seg in listen(
            provider=self._provider,
            audio_url=self._audio_url,
            speaker_id=self._speaker_id,
            event_id=self._event_id,
        ):
            yield self.adapt_segment(seg)
