"""Polling orchestrator — drives all configured figures × sources.

Wave 5 Task 5.2 — the long-running async loop that wakes each tweet source
on its `poll_interval_min`, fans the resulting `FigurePost`s through that
figure's `FigureDeviationDispatcher`, and persists state across cycles.

Audio sources are NOT driven from here — they're event-driven (run when
a Fed event is scheduled). This orchestrator is for non-realtime sources
only (X API, future Sonar tweet polling).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path

from castelino.config import (
    FigureDeviationCfg,
    Settings,
    TrackedFigureCfg,
    TrackedFigureSourceCfg,
)
from castelino.triggers.figure_deviation.dispatcher import (
    FigureDeviationDispatcher,
    LexiconBinding,
    StageBProtocol,
)
from castelino.triggers.figure_deviation.models import FigureDeviationTrigger
from castelino.triggers.figure_deviation.source.base import FigurePostSource
from castelino.triggers.figure_deviation.source.x_api import XApiTweetSource

log = logging.getLogger(__name__)


SourceFactory = Callable[[TrackedFigureSourceCfg], FigurePostSource]


@dataclass
class PollSchedule:
    """Tracks when each (figure_id, source_index) pair was last polled."""
    last_polled: dict[tuple[str, int], datetime]


def default_source_factory(
    settings: Settings,
) -> SourceFactory:
    """Default factory: returns the right source impl based on cfg.type."""
    bearer = settings.x_api_bearer_token

    def _factory(src_cfg: TrackedFigureSourceCfg) -> FigurePostSource:
        if src_cfg.type == "x_api":
            if not bearer:
                raise RuntimeError(
                    "X_API_BEARER_TOKEN missing — required for x_api sources",
                )
            return XApiTweetSource(
                bearer_token=bearer,
                base_url=settings.x_api.base_url,
                timeout_sec=settings.x_api.request_timeout_sec,
            )
        if src_cfg.type == "audio":
            raise RuntimeError(
                "Audio sources are event-driven, not polled. They run via "
                "the existing fed-event-calendar listener, not the polling "
                "orchestrator.",
            )
        if src_cfg.type == "sonar_tweet":
            raise NotImplementedError(
                "sonar_tweet source is reserved for future use — not yet "
                "implemented.",
            )
        raise ValueError(f"Unknown source type: {src_cfg.type}")

    return _factory


class FigureDeviationPollingOrchestrator:
    """Long-running async loop that polls all non-audio sources on cadence.

    Lifecycle:
      • `run()` blocks until cancelled; each tick, polls every figure × source
        whose `poll_interval_min` has elapsed since its last poll.
      • Per-figure FigureDeviationDispatchers are constructed lazily on first
        post and reused across ticks (in-memory rolling-window state).
      • Errors in one figure's source are logged and isolated — they do not
        crash the orchestrator.
    """

    # Tick frequency: how often the loop wakes to check schedules. Should be
    # smaller than the smallest configured poll_interval_min.
    _TICK_SECONDS = 30

    def __init__(
        self,
        *,
        cfg: FigureDeviationCfg,
        source_factory: SourceFactory,
        baseline_dir: Path,
        lexicon_dir: Path,
        stage_b: StageBProtocol,
        emitter: Callable[[FigureDeviationTrigger], None] | Callable[
            [FigureDeviationTrigger], Awaitable[None],
        ],
    ) -> None:
        self._cfg = cfg
        self._source_factory = source_factory
        self._baseline_dir = baseline_dir
        self._lexicon_dir = lexicon_dir
        self._stage_b = stage_b
        self._emitter = emitter
        self._dispatchers: dict[str, FigureDeviationDispatcher] = {}
        self._schedule = PollSchedule(last_polled={})

    def _get_dispatcher(
        self, figure: TrackedFigureCfg,
    ) -> FigureDeviationDispatcher:
        if figure.id not in self._dispatchers:
            bindings = [
                LexiconBinding(
                    name=lex.name,
                    threshold_sigma=lex.threshold_sigma,
                    window_size=lex.window_size,
                    directional_tags_positive=list(lex.directional_tags_positive),
                    directional_tags_negative=list(lex.directional_tags_negative),
                )
                for lex in figure.lexicons
            ]
            self._dispatchers[figure.id] = FigureDeviationDispatcher(
                figure_id=figure.id,
                lexicon_bindings=bindings,
                lexicon_dir=self._lexicon_dir,
                baseline_dir=self._baseline_dir,
                stage_b=self._stage_b,
                emitter=self._emitter,
            )
        return self._dispatchers[figure.id]

    def _due_for_poll(
        self, figure_id: str, src_idx: int, interval_min: int, now: datetime,
    ) -> bool:
        last = self._schedule.last_polled.get((figure_id, src_idx))
        if last is None:
            return True
        elapsed_min = (now - last).total_seconds() / 60.0
        return elapsed_min >= interval_min

    async def tick(self, now: datetime | None = None) -> int:
        """One scheduling pass — runs polls for everything due. Returns the
        number of (figure, source) pairs polled this tick. Useful for tests
        that don't want to spin the full event loop."""
        if not self._cfg.enabled:
            return 0
        now = now or datetime.now(UTC)
        polled = 0
        for figure in self._cfg.figures:
            for src_idx, src_cfg in enumerate(figure.sources):
                if src_cfg.type == "audio":
                    continue  # event-driven, not polled
                interval = src_cfg.poll_interval_min or self._cfg.poll_interval_min
                if not self._due_for_poll(figure.id, src_idx, interval, now):
                    continue
                await self._poll_one(figure, src_idx, src_cfg)
                self._schedule.last_polled[(figure.id, src_idx)] = now
                polled += 1
        return polled

    async def _poll_one(
        self,
        figure: TrackedFigureCfg,
        src_idx: int,
        src_cfg: TrackedFigureSourceCfg,
    ) -> None:
        try:
            source = self._source_factory(src_cfg)
        except Exception:
            log.exception(
                "Could not construct source for %s source[%d]", figure.id, src_idx,
            )
            return
        dispatcher = self._get_dispatcher(figure)
        try:
            async for post in source.stream(figure, src_cfg):
                try:
                    await dispatcher.handle_post(post)
                except Exception:
                    log.exception(
                        "Dispatcher raised handling post %s for %s",
                        post.event_id, figure.id,
                    )
        except Exception:
            log.exception(
                "Source stream raised for %s source[%d]", figure.id, src_idx,
            )

    async def run(self) -> None:
        """Main loop. Cancellable via standard asyncio task cancellation."""
        log.info(
            "FigureDeviationPollingOrchestrator running with %d figures",
            len(self._cfg.figures),
        )
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Unhandled exception in polling tick")
            await asyncio.sleep(self._TICK_SECONDS)
