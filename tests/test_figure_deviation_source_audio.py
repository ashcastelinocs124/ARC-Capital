"""Wave 2 Task 2.2 — verify the source-pluggability layer.

The audio path is now one implementation of `FigurePostSource`; an X API
implementation will land in Wave 5 and conform to the same ABC. The shared
machinery downstream consumes only `FigurePost` objects.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from castelino.triggers.figure_deviation.models import FigurePost


# ────────────────────────── FigurePostSource ABC ─────────────────────────────


def test_figure_post_source_is_abstract():
    from castelino.triggers.figure_deviation.source.base import FigurePostSource

    assert inspect.isabstract(FigurePostSource)
    # Must declare async `stream` as an abstract method
    assert "stream" in FigurePostSource.__abstractmethods__


def test_figure_post_source_subclass_must_implement_stream():
    from castelino.triggers.figure_deviation.source.base import FigurePostSource

    class IncompleteSource(FigurePostSource):
        pass

    with pytest.raises(TypeError, match="abstract"):
        IncompleteSource()  # cannot instantiate without `stream`


# ────────────────────────── AudioFigurePostSource ─────────────────────────────


@pytest.mark.asyncio
async def test_audio_source_adapts_speech_segment_to_figure_post():
    """A SpeechSegment from the existing listener becomes a FigurePost with
    source='audio' and event_id preserved."""
    from castelino.triggers.figure_deviation.source.audio import AudioFigurePostSource
    from castelino.triggers.figure_deviation.speech_models import SpeechSegment

    seg = SpeechSegment(
        speaker_id="powell",
        text="The committee remains data-dependent.",
        timestamp=datetime(2026, 5, 8, 14, 30, tzinfo=UTC),
        event_id="fomc-2026-05-08",
    )
    post = AudioFigurePostSource.adapt_segment(seg)
    assert isinstance(post, FigurePost)
    assert post.figure_id == "powell"
    assert post.text == "The committee remains data-dependent."
    assert post.source == "audio"
    assert post.event_id == "fomc-2026-05-08"
    assert post.ts == seg.timestamp


@pytest.mark.asyncio
async def test_audio_source_stream_yields_figure_posts_from_segment_iterator():
    """The source's `stream()` method consumes an iterator of SpeechSegments
    (whatever the provider produces) and yields adapted FigurePosts."""
    from castelino.triggers.figure_deviation.source.audio import AudioFigurePostSource
    from castelino.triggers.figure_deviation.speech_models import SpeechSegment

    async def fake_listener():
        yield SpeechSegment(
            speaker_id="powell",
            text="Inflation remains elevated.",
            timestamp=datetime(2026, 5, 8, 14, 30, tzinfo=UTC),
            event_id="fomc-2026-05-08",
        )
        yield SpeechSegment(
            speaker_id="powell",
            text="We will be data-dependent.",
            timestamp=datetime(2026, 5, 8, 14, 31, tzinfo=UTC),
            event_id="fomc-2026-05-08",
        )

    posts = [p async for p in AudioFigurePostSource.from_segment_stream(
        fake_listener(),
    )]
    assert len(posts) == 2
    assert all(isinstance(p, FigurePost) for p in posts)
    assert all(p.source == "audio" for p in posts)
    assert posts[0].text == "Inflation remains elevated."
    assert posts[1].text == "We will be data-dependent."


def test_audio_source_class_subclasses_the_abc():
    """Sanity: the audio source declares its parent so future polymorphism works."""
    from castelino.triggers.figure_deviation.source.audio import AudioFigurePostSource
    from castelino.triggers.figure_deviation.source.base import FigurePostSource

    assert issubclass(AudioFigurePostSource, FigurePostSource)
