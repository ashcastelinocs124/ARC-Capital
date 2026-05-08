from castelino.triggers.speech.deviation import RollingWindow, compute_deviation
from castelino.triggers.speech.models import BaselineVector

BL = BaselineVector(
    hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
    key_phrase_frequencies={}, hedging_density=0.18,
)


def test_window_keeps_only_last_n():
    w = RollingWindow(size=3)
    for s in [0.1, 0.2, 0.3, 0.4]:
        w.push(s)
    assert w.values() == [0.2, 0.3, 0.4]


def test_window_min_required_blocks_score():
    w = RollingWindow(size=5, min_required=3)
    w.push(0.5)
    assert w.mean() is None
    w.push(0.5); w.push(0.5)
    assert w.mean() == 0.5


def test_compute_deviation_against_dovish_baseline():
    sigma = compute_deviation(window_mean=0.38, baseline=BL)
    assert 2.5 < sigma < 2.8


def test_compute_deviation_returns_zero_when_at_baseline():
    sigma = compute_deviation(window_mean=-0.15, baseline=BL)
    assert sigma == 0.0
