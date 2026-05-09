"""Stream listener: STT events → SpeechSegment per complete sentence."""
from __future__ import annotations

from collections.abc import AsyncIterator

from castelino.triggers.figure_deviation.speech_models import SpeechSegment
from castelino.triggers.figure_deviation.scorer import split_sentences
from castelino.triggers.figure_deviation.stt import SpeechToTextProvider


async def listen(
    *,
    provider: SpeechToTextProvider,
    audio_url: str,
    speaker_id: str,
    event_id: str,
) -> AsyncIterator[SpeechSegment]:
    """Yield one SpeechSegment per complete sentence from the live stream."""
    async for ev in provider.stream(audio_url=audio_url):
        if not ev.is_final:
            continue
        for sentence in split_sentences(ev.text):
            yield SpeechSegment(
                speaker_id=speaker_id, text=sentence,
                timestamp=ev.timestamp, event_id=event_id,
            )
