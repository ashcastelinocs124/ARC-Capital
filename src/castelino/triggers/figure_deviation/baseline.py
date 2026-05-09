"""Aggregate scored speeches into a time-weighted BaselineVector."""
from __future__ import annotations

import math
from datetime import datetime, UTC

from castelino.triggers.figure_deviation.speech_models import BaselineVector, ScoredSpeech


def _months_ago(d: datetime) -> float:
    delta = datetime.now(UTC) - d
    return delta.total_seconds() / (30.44 * 86400)


def build_baseline(
    speeches: list[ScoredSpeech],
    *,
    half_life_months: float = 6.0,
    key_phrase_frequencies: dict[str, float] | None = None,
    hedging_density: float = 0.0,
) -> BaselineVector:
    if not speeches:
        raise ValueError("Cannot build baseline from empty speech list")

    decay = math.log(2.0) / half_life_months
    weights = [math.exp(-decay * _months_ago(s.date)) for s in speeches]
    total_w = sum(weights)
    mean = sum(w * s.score for w, s in zip(weights, speeches)) / total_w

    var = sum(w * (s.score - mean) ** 2 for w, s in zip(weights, speeches)) / total_w
    std = math.sqrt(var) or 0.05  # floor to avoid divide-by-zero in z-score later

    return BaselineVector(
        hawkish_dovish_mean=mean,
        hawkish_dovish_std=std,
        key_phrase_frequencies=key_phrase_frequencies or {},
        hedging_density=hedging_density,
    )
