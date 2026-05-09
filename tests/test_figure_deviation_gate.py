"""Wave 3 Task 3.3 — per-(figure x lexicon) deviation gate.

The existing single-baseline `compute_deviation()` helper is kept for the
speech tests. The new `DeviationGate` class maintains an independent rolling
window per `(figure_id, lexicon_name)` pair so a single post fans across
multiple lexicons in parallel without cross-contamination.
"""
from __future__ import annotations

import pytest


# ────────────────────────── independent windows per lexicon ─────────────────


def test_deviation_gate_isolates_windows_per_lexicon():
    from castelino.triggers.figure_deviation.gate import DeviationGate

    gate = DeviationGate()
    # Feed the trade lexicon with high scores
    for v in [0.6, 0.7, 0.8]:
        result = gate.update(
            figure_id="trump",
            lexicon="trade_protectionist_v1",
            score=v,
            baseline_mean=0.1,
            baseline_std=0.2,
            window_size=3,
            threshold_sigma=1.5,
        )
    assert result.crossed is True
    assert result.direction == "positive"
    # Same time, fed lexicon stays low — must NOT cross
    for v in [0.0, 0.05, 0.0]:
        r2 = gate.update(
            figure_id="trump",
            lexicon="fed_pressure_v1",
            score=v,
            baseline_mean=0.0,
            baseline_std=0.1,
            window_size=3,
            threshold_sigma=1.5,
        )
    assert r2.crossed is False


def test_deviation_gate_isolates_windows_per_figure():
    """Powell's rolling window does not leak into Bullard's."""
    from castelino.triggers.figure_deviation.gate import DeviationGate

    gate = DeviationGate()
    # Powell hits high
    for v in [0.6, 0.7, 0.8]:
        gate.update(
            figure_id="powell", lexicon="hawkish_dovish_v1",
            score=v, baseline_mean=0.0, baseline_std=0.2,
            window_size=3, threshold_sigma=1.5,
        )
    # Bullard fresh window — first score
    r = gate.update(
        figure_id="bullard", lexicon="hawkish_dovish_v1",
        score=0.5, baseline_mean=0.4, baseline_std=0.15,
        window_size=3, threshold_sigma=1.5,
    )
    # Bullard's window only has 1 entry; must report not crossed
    # (insufficient samples) rather than reusing Powell's window
    assert r.crossed is False
    assert len(r.window) == 1


# ────────────────────────── threshold semantics ─────────────────────────────


def test_deviation_gate_does_not_fire_below_threshold():
    from castelino.triggers.figure_deviation.gate import DeviationGate

    gate = DeviationGate()
    # window mean = 0.1, baseline 0.0/0.1 → z = 1.0
    for v in [0.05, 0.10, 0.15]:
        r = gate.update(
            figure_id="trump", lexicon="x_v1",
            score=v, baseline_mean=0.0, baseline_std=0.1,
            window_size=3, threshold_sigma=1.5,
        )
    assert r.crossed is False
    assert r.z == pytest.approx(1.0, rel=1e-3)


def test_deviation_gate_fires_above_threshold():
    from castelino.triggers.figure_deviation.gate import DeviationGate

    gate = DeviationGate()
    # window mean = 0.4, baseline 0.0/0.1 → z = 4.0
    for v in [0.4, 0.4, 0.4]:
        r = gate.update(
            figure_id="trump", lexicon="x_v1",
            score=v, baseline_mean=0.0, baseline_std=0.1,
            window_size=3, threshold_sigma=1.5,
        )
    assert r.crossed is True
    assert r.z == pytest.approx(4.0, rel=1e-3)
    assert r.direction == "positive"


def test_deviation_gate_negative_direction():
    from castelino.triggers.figure_deviation.gate import DeviationGate

    gate = DeviationGate()
    # window mean = -0.4, baseline 0.0/0.1 → z = -4.0 (dovish deviation)
    for v in [-0.3, -0.4, -0.5]:
        r = gate.update(
            figure_id="powell", lexicon="hawkish_dovish_v1",
            score=v, baseline_mean=0.0, baseline_std=0.1,
            window_size=3, threshold_sigma=1.5,
        )
    assert r.crossed is True
    assert r.z == pytest.approx(-4.0, rel=1e-3)
    assert r.direction == "negative"


# ────────────────────────── min-samples / under-filled window ──────────────


def test_deviation_gate_does_not_fire_with_partial_window():
    """A 3-window with only 1 score must not fire even if that one score is
    extreme — z-scoring on one sample is meaningless."""
    from castelino.triggers.figure_deviation.gate import DeviationGate

    gate = DeviationGate()
    r = gate.update(
        figure_id="trump", lexicon="x_v1",
        score=10.0, baseline_mean=0.0, baseline_std=0.1,
        window_size=3, threshold_sigma=1.5,
    )
    assert r.crossed is False


# ────────────────────────── movement filter ────────────────────────────────


def test_deviation_gate_does_not_fire_when_window_returning_to_baseline():
    """If the window crossed the threshold while moving away from baseline,
    fire. If it crosses again while moving back toward baseline (e.g., during
    decay), do NOT fire — the signal is the move, not the level."""
    from castelino.triggers.figure_deviation.gate import DeviationGate

    gate = DeviationGate()
    # Climb above threshold (3 increasing values, hitting z>1.5)
    for v in [0.4, 0.45, 0.50]:
        r1 = gate.update(
            figure_id="trump", lexicon="x_v1",
            score=v, baseline_mean=0.0, baseline_std=0.1,
            window_size=3, threshold_sigma=1.5,
        )
    assert r1.crossed is True
    # Window decays back: 0.50, 0.40, 0.30 → mean still 0.40, z=4.0,
    # but window is moving DOWN — not a fresh crossing event
    for v in [0.40, 0.30]:
        r2 = gate.update(
            figure_id="trump", lexicon="x_v1",
            score=v, baseline_mean=0.0, baseline_std=0.1,
            window_size=3, threshold_sigma=1.5,
        )
    # Last update: window=[0.50, 0.40, 0.30], mean=0.40, z=4.0,
    # but trajectory is heading back to baseline — should not refire
    assert r2.crossed is False
