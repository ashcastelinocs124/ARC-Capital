"""Stage A — per-(figure x lexicon) rolling-window deviation gate.

The existing `deviation.py::compute_deviation()` is a single-shot z-score
helper still used by the speech listener. This module adds the stateful
multi-figure / multi-lexicon counterpart for the generalised engine.

Each `(figure_id, lexicon_name)` pair gets its own rolling buffer. A single
`FigurePost` is fed into every lexicon configured on its figure, and each
gate evaluates independently.

The "movement filter" prevents re-firing as a window decays back through
the threshold: a Stage A pass requires not only that |z| > threshold, but
that the trajectory is moving AWAY from baseline (or at least not moving
back toward it). This is what distinguishes "Powell turning hawkish" from
"Powell who has been hawkish slowly normalising".
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class StageAResult:
    """Outcome of one update call. `crossed` is the gate decision."""

    crossed: bool
    z: float
    direction: str            # "positive" | "negative" | "neutral"
    window: list[float]


class DeviationGate:
    """Stateful Stage A gate keyed on `(figure_id, lexicon_name)`.

    Rolling windows are stored per pair so a single post evaluating against
    three lexicons updates three independent windows. Min-required samples
    in the window before evaluation: 3 (z-score with fewer samples is noise).
    """

    _MIN_REQUIRED = 3

    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], deque[float]] = {}

    def _get_window(
        self, *, figure_id: str, lexicon: str, size: int,
    ) -> deque[float]:
        key = (figure_id, lexicon)
        win = self._windows.get(key)
        if win is None or win.maxlen != size:
            win = deque(maxlen=size)
            self._windows[key] = win
        return win

    def update(
        self,
        *,
        figure_id: str,
        lexicon: str,
        score: float,
        baseline_mean: float,
        baseline_std: float,
        window_size: int,
        threshold_sigma: float,
    ) -> StageAResult:
        """Push a new score and emit the resulting gate decision.

        Returns `StageAResult.crossed = True` only when:
          1. The window has at least MIN_REQUIRED samples;
          2. |z| > threshold_sigma;
          3. The trajectory is moving away from (or stable at) the
             window-mean direction — not returning to baseline.
        """
        if baseline_std <= 0:
            # A zero-std baseline would produce an infinite z. Treat as
            # uninitialised — never fire.
            win = self._get_window(
                figure_id=figure_id, lexicon=lexicon, size=window_size,
            )
            win.append(score)
            return StageAResult(
                crossed=False, z=0.0, direction="neutral", window=list(win),
            )

        win = self._get_window(
            figure_id=figure_id, lexicon=lexicon, size=window_size,
        )
        win.append(score)
        values = list(win)

        if len(values) < self._MIN_REQUIRED:
            return StageAResult(
                crossed=False, z=0.0, direction="neutral", window=values,
            )

        window_mean = sum(values) / len(values)
        z = (window_mean - baseline_mean) / baseline_std
        direction = (
            "positive" if z > 0 else "negative" if z < 0 else "neutral"
        )

        threshold_passed = abs(z) > threshold_sigma
        moving_away = self._is_moving_away_from_baseline(
            values=values, baseline_mean=baseline_mean,
        )
        crossed = threshold_passed and moving_away

        return StageAResult(
            crossed=crossed, z=z, direction=direction, window=values,
        )

    @staticmethod
    def _is_moving_away_from_baseline(
        *, values: list[float], baseline_mean: float,
    ) -> bool:
        """True if the most recent value is at least as far from baseline
        as the value immediately before it. Filters out windows that
        crossed the threshold while DECAYING back toward baseline."""
        if len(values) < 2:
            return True
        last = values[-1]
        prev = values[-2]
        last_dist = abs(last - baseline_mean)
        prev_dist = abs(prev - baseline_mean)
        return last_dist >= prev_dist
