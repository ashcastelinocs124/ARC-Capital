import pytest
from datetime import datetime, timedelta, UTC
from castelino.triggers.figure_deviation.baseline import build_baseline
from castelino.triggers.figure_deviation.speech_models import ScoredSpeech


def _ss(score: float, days_ago: int) -> ScoredSpeech:
    return ScoredSpeech(
        speech_id=f"s-{days_ago}",
        date=datetime.now(UTC) - timedelta(days=days_ago),
        score=score,
        n_policy_sentences=10,
    )


def test_baseline_unweighted_mean_when_half_life_is_huge():
    speeches = [_ss(0.0, 30), _ss(-0.4, 60), _ss(0.4, 90)]
    bv = build_baseline(speeches, half_life_months=10000)
    assert bv.hawkish_dovish_mean == pytest.approx(0.0, abs=1e-3)


def test_baseline_recent_weighted_higher():
    speeches = [_ss(+1.0, 1), _ss(-1.0, 365)]
    bv = build_baseline(speeches, half_life_months=6)
    assert bv.hawkish_dovish_mean > 0.5


def test_baseline_std_tracks_dispersion():
    tight = [_ss(0.1, i) for i in range(1, 11)]
    wide = [_ss(0.5 if i % 2 else -0.3, i) for i in range(1, 11)]
    assert build_baseline(tight, half_life_months=6).hawkish_dovish_std < \
           build_baseline(wide, half_life_months=6).hawkish_dovish_std


def test_baseline_empty_raises():
    with pytest.raises(ValueError):
        build_baseline([], half_life_months=6)
