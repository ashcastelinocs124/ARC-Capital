"""Sentence-level hawkish/dovish scorer.

The scoring function is the load-bearing invariant: identical scoring is used
for both the offline persona baseline and the live listener, so z-score
deviations compare like-for-like. If the lexicon changes, version it (v2,
v3, ...) and rebuild every persona from the historical corpus.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Lexicon:
    version: str
    hawkish_phrases: dict[str, float]
    dovish_phrases: dict[str, float]
    hedges: tuple[str, ...]


def load_lexicon(version: str = "hawkish_dovish_v1") -> Lexicon:
    path = Path("data/lexicons") / f"{version}.yaml"
    raw = yaml.safe_load(path.read_text())
    return Lexicon(
        version=raw["version"],
        hawkish_phrases=dict(raw["hawkish_phrases"]),
        dovish_phrases=dict(raw["dovish_phrases"]),
        hedges=tuple(raw["hedges"]),
    )


def score_sentence(text: str, *, lexicon: Lexicon) -> float:
    """Score a sentence on hawkish-dovish in [-1, +1]. Hedges dampen magnitude."""
    lowered = text.lower()
    raw = 0.0
    for phrase, weight in lexicon.hawkish_phrases.items():
        if phrase in lowered:
            raw += weight
    for phrase, weight in lexicon.dovish_phrases.items():
        if phrase in lowered:
            raw += weight  # weight is already negative

    hedge_count = sum(1 for h in lexicon.hedges if h in lowered)
    if hedge_count > 0:
        raw *= max(0.4, 1.0 - 0.2 * hedge_count)

    return max(-1.0, min(1.0, raw))


@dataclass(frozen=True)
class SpeechScoreResult:
    score: float
    n_policy_sentences: int


POLICY_RELEVANT_THRESHOLD = 0.05


def score_speech(sentences: list[str], *, lexicon: Lexicon) -> SpeechScoreResult:
    """Aggregate a speech: mean of policy-relevant sentence scores."""
    scored = [score_sentence(s, lexicon=lexicon) for s in sentences]
    policy = [x for x in scored if abs(x) > POLICY_RELEVANT_THRESHOLD]
    if not policy:
        return SpeechScoreResult(score=0.0, n_policy_sentences=0)
    return SpeechScoreResult(
        score=sum(policy) / len(policy),
        n_policy_sentences=len(policy),
    )
