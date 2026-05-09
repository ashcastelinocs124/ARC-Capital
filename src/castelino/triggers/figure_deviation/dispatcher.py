"""Multi-lexicon dispatcher — fans a single FigurePost across N lexicons.

Wave 3 Task 3.4 — wires together the Wave 3 Task 3.1-3.3 components into
the per-figure runtime that handles incoming posts:

    Scorer (3.1) → BaselineStore (3.2) → DeviationGate (3.3)
                                        ↓
                                Stage B (Wave 7)
                                        ↓
                              FigureDeviationTrigger

Construction binds a single tracked figure to its configured lexicons. Each
incoming post is scored against every binding in parallel; each binding's
own rolling window is updated; bindings whose Stage A passes invoke Stage B;
confirmed deviations emit a trigger via the supplied callback.

Cooldown is per `(figure_id, lexicon_name, event_id)` triple — the same
post hitting the dispatcher twice never produces duplicate emissions on the
same lexicon, but a single post legitimately emits once per lexicon it
confirmed on.

Stage B is injected (so Wave 7 can wire in the real LLM gate). For Wave 3
the test suite uses a fake that always confirms, isolating fan-out + gate
behaviour from LLM concerns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from castelino.triggers.figure_deviation.baseline_store import BaselineStore
from castelino.triggers.figure_deviation.gate import DeviationGate, StageAResult
from castelino.triggers.figure_deviation.models import (
    FigureDeviationTrigger,
    FigurePost,
)
from castelino.triggers.figure_deviation.scorer import Scorer


@dataclass(frozen=True)
class LexiconBinding:
    """One lexicon as configured on a tracked figure.

    Mirrors `castelino.config.LexiconCfg` but as a runtime value passed into
    the dispatcher (avoids the dispatcher reading the full Settings).
    """

    name: str
    threshold_sigma: float
    window_size: int
    directional_tags_positive: list[str] = field(default_factory=list)
    directional_tags_negative: list[str] = field(default_factory=list)


class StageBProtocol(Protocol):
    """Stage B confirmation gate — injected dependency.

    Real implementation lands in Wave 7 (LLM call with FigureProfile
    retrieval); for Wave 3 a stub fulfils this interface.
    """

    async def confirm_deviation(
        self,
        *,
        figure_id: str,
        lexicon: str,
        post: FigurePost,
        z: float,
        window: list[float],
    ) -> bool:  # True = confirm, False = veto
        ...


Emitter = Callable[[FigureDeviationTrigger], None] | Callable[
    [FigureDeviationTrigger], Awaitable[None],
]


class FigureDeviationDispatcher:
    """Per-figure runtime that scores incoming posts across N lexicons,
    runs each through the Stage A gate, escalates the survivors to Stage B,
    and emits triggers on confirmation.

    Cooldown state is in-process and per-dispatcher; persistent cooldown
    across restarts is a Wave 5/8 concern.
    """

    def __init__(
        self,
        *,
        figure_id: str,
        lexicon_bindings: list[LexiconBinding],
        lexicon_dir: Path,
        baseline_dir: Path,
        stage_b: StageBProtocol,
        emitter: Emitter,
    ) -> None:
        self._figure_id = figure_id
        self._bindings = lexicon_bindings
        self._scorer = Scorer(lexicon_dir=lexicon_dir)
        self._baselines = BaselineStore(
            base_dir=baseline_dir, lexicon_dir=lexicon_dir,
        )
        self._gate = DeviationGate()
        self._stage_b = stage_b
        self._emitter = emitter
        # Cooldown set: (figure_id, lexicon_name, event_id) we've emitted on
        self._emitted: set[tuple[str, str, str]] = set()

    async def handle_post(self, post: FigurePost) -> None:
        """Run one post through every configured lexicon. Each binding
        evaluates independently; multiple emissions are possible from one
        post (one per lexicon it confirms on)."""
        for binding in self._bindings:
            await self._handle_one_lexicon(post, binding)

    async def _handle_one_lexicon(
        self, post: FigurePost, binding: LexiconBinding,
    ) -> None:
        # Cooldown: skip if we've already emitted on this lexicon × event
        cooldown_key = (self._figure_id, binding.name, post.event_id)
        if cooldown_key in self._emitted:
            return

        # Score the post on this lexicon
        score = self._scorer.score_post(
            text=post.text, lexicon_name=binding.name,
        )

        # Look up the figure's baseline for this lexicon (raises if missing)
        baseline = self._baselines.load(
            figure_id=self._figure_id, lexicon_name=binding.name,
        )

        # Stage A: rolling-window z-score gate
        stage_a = self._gate.update(
            figure_id=self._figure_id,
            lexicon=binding.name,
            score=score.value,
            baseline_mean=baseline.mean,
            baseline_std=baseline.std,
            window_size=binding.window_size,
            threshold_sigma=binding.threshold_sigma,
        )
        if not stage_a.crossed:
            return

        # Stage B: LLM confirmation (or stub in tests)
        confirmed = await self._stage_b.confirm_deviation(
            figure_id=self._figure_id,
            lexicon=binding.name,
            post=post,
            z=stage_a.z,
            window=stage_a.window,
        )
        if not confirmed:
            return

        # Emit
        trigger = self._build_trigger(
            binding=binding,
            stage_a=stage_a,
            decisive_phrase=post.text,
            event_id=post.event_id,
            confidence=0.8,  # placeholder — Stage B will return real value
        )
        result = self._emitter(trigger)
        # Support sync or async emitters
        if hasattr(result, "__await__"):
            await result
        self._emitted.add(cooldown_key)

    def _build_trigger(
        self,
        *,
        binding: LexiconBinding,
        stage_a: StageAResult,
        decisive_phrase: str,
        event_id: str,
        confidence: float,
    ) -> FigureDeviationTrigger:
        if stage_a.direction == "positive":
            tags = list(binding.directional_tags_positive)
        elif stage_a.direction == "negative":
            tags = list(binding.directional_tags_negative)
        else:
            tags = []
        return FigureDeviationTrigger(
            figure_id=self._figure_id,
            lexicon=binding.name,
            z=stage_a.z,
            direction=stage_a.direction,
            directional_tags=tags,
            decisive_phrase=decisive_phrase,
            confirmed_by_llm=True,
            confidence=confidence,
            window_post_ids=[event_id],
        )
