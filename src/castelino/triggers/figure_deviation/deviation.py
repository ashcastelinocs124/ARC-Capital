"""Rolling window + z-score deviation calculator (Stage A)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from castelino.triggers.figure_deviation.speech_models import BaselineVector


@dataclass
class RollingWindow:
    size: int
    min_required: int = 3
    _buf: deque = field(default=None)

    def __post_init__(self):
        self._buf = deque(maxlen=self.size)

    def push(self, score: float) -> None:
        self._buf.append(score)

    def values(self) -> list[float]:
        return list(self._buf)

    def mean(self) -> float | None:
        if len(self._buf) < self.min_required:
            return None
        return sum(self._buf) / len(self._buf)


def compute_deviation(*, window_mean: float, baseline: BaselineVector) -> float:
    """Z-score: how many sigma is the rolling window from the speaker's baseline?"""
    return (window_mean - baseline.hawkish_dovish_mean) / baseline.hawkish_dovish_std
