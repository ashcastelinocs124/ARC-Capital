"""Real-time emitter: ingests SpeechSegments, emits TriggerRecords on shifts.

Structural guarantees:
- Threshold check enforced BEFORE LLM call (no LLM cost on calm speech).
- Cooldown caps emissions at one per event_id.
- Both Stage A (|sigma| > threshold) AND Stage B (LLM is_shift=True) must agree.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from castelino.agents.base import LLMClient
from castelino.memory.schemas import TriggerRecord, TriggerSource
from castelino.triggers.speech.deviation import RollingWindow, compute_deviation
from castelino.triggers.speech.llm_gate import (
    SpeechShiftClassification,
    classify_speech_shift,
)
from castelino.triggers.speech.models import BaselineVector, SpeechSegment
from castelino.triggers.speech.scorer import (
    POLICY_RELEVANT_THRESHOLD,
    load_lexicon,
    score_sentence,
)

log = logging.getLogger(__name__)


@dataclass
class SpeechTriggerEmitter:
    speaker_id: str
    full_name: str
    baseline: BaselineVector
    threshold_sigma: float
    llm_client: LLMClient
    lexicon_version: str = "hawkish_dovish_v1"
    window_size: int = 5
    triggers: list[TriggerRecord] = field(default_factory=list)
    _fired_event_ids: set[str] = field(default_factory=set)
    _windows_by_event: dict[str, RollingWindow] = field(default_factory=dict)
    _texts_by_event: dict[str, list[str]] = field(default_factory=dict)
    _lexicon: object = None

    def __post_init__(self):
        self._lexicon = load_lexicon(self.lexicon_version)

    def ingest(self, segment: SpeechSegment) -> None:
        if segment.event_id in self._fired_event_ids:
            return
        score = score_sentence(segment.text, lexicon=self._lexicon)
        win = self._windows_by_event.setdefault(
            segment.event_id,
            RollingWindow(size=self.window_size, min_required=3),
        )
        texts = self._texts_by_event.setdefault(segment.event_id, [])
        if abs(score) > POLICY_RELEVANT_THRESHOLD:
            win.push(score)
            texts.append(segment.text)
            if len(texts) > self.window_size:
                texts.pop(0)
        win_mean = win.mean()
        if win_mean is None:
            return
        sigma = compute_deviation(window_mean=win_mean, baseline=self.baseline)
        if abs(sigma) <= self.threshold_sigma:
            return
        verdict = classify_speech_shift(
            client=self.llm_client,
            full_name=self.full_name,
            baseline=self.baseline,
            rolling_window_text=" ".join(texts),
        )
        if not verdict.is_shift:
            log.info("speech: sigma=%.2f exceeded but LLM disagreed", sigma)
            return
        self._emit(segment, sigma, verdict)

    def _emit(
        self,
        segment: SpeechSegment,
        sigma: float,
        verdict: SpeechShiftClassification,
    ) -> None:
        trg = TriggerRecord(
            source=TriggerSource.SPEECH_DEVIATION,
            headline=f"{self.full_name}: {verdict.direction} shift mid-speech",
            significance=min(0.95, 0.6 + 0.3 * verdict.magnitude),
            asset_classes_affected=["rates", "equities", "fx"],
            raw_event_data={
                "speaker_id": self.speaker_id,
                "deviation_sigma": sigma,
                "decisive_phrase": verdict.decisive_phrase,
                "transcript_window": " ".join(self._texts_by_event[segment.event_id]),
                "event_id": segment.event_id,
            },
            one_sentence_reason=(
                f"{self.full_name} shifted {verdict.direction} "
                f"({sigma:+.1f}sigma): «{verdict.decisive_phrase}»"
            ),
        )
        self.triggers.append(trg)
        self._fired_event_ids.add(segment.event_id)
