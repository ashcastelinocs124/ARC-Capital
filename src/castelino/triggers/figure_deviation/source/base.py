"""Abstract base for any figure-post source.

Every concrete source (audio, x_api, sonar_tweet) implements this interface so
the orchestrator can poll/stream from N heterogeneous figures uniformly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from castelino.triggers.figure_deviation.models import FigurePost


class FigurePostSource(ABC):
    """Stream of `FigurePost` objects from one source for one figure.

    Concrete implementations vary widely: `AudioFigurePostSource` wraps a
    Deepgram STT pipeline emitting one `FigurePost` per transcribed sentence;
    a future `XApiTweetSource` will poll the X API and emit one `FigurePost`
    per new tweet. Both produce the same downstream shape.
    """

    @abstractmethod
    async def stream(self, figure, source_cfg) -> AsyncIterator[FigurePost]:
        """Yield `FigurePost`s for the given tracked figure.

        Implementations may run continuously (audio listening) or fire on a
        polling cadence (X API). The orchestrator is responsible for spawning
        and lifecycle-managing the resulting async iterator.
        """
        raise NotImplementedError
        yield  # pragma: no cover — make this an async generator at typecheck
