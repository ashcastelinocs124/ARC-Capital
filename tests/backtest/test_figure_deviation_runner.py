import pytest
from castelino.backtest_regression.runner import run_figure_deviation_case


def test_positive_case_passes_when_score_is_hawkish_enough():
    fixture = {
        "case_id": "synth_hawk",
        "lexicon": "hawkish_dovish_v1",
        "transcript_excerpt": "Further firming of policy is warranted given persistent inflation.",
        "expected": {
            "value_sign": "positive",
            "abs_value_min": 0.10,
            "must_hit_terms_any": ["further firming", "warranted"],
        },
    }
    result = run_figure_deviation_case(fixture)
    assert result.passed, f"actual={result.actual}, notes={result.notes}"


def test_negative_case_passes_when_score_is_calm():
    fixture = {
        "case_id": "synth_calm",
        "lexicon": "hawkish_dovish_v1",
        "transcript_excerpt": "Today the Committee discussed the economic outlook. Members noted recent activity.",
        "expected": {"abs_value_max": 0.10},
    }
    result = run_figure_deviation_case(fixture)
    assert result.passed, f"actual={result.actual}, notes={result.notes}"


def test_diverging_sign_fails():
    fixture = {
        "case_id": "wrong_sign",
        "lexicon": "hawkish_dovish_v1",
        "transcript_excerpt": "We will be patient and accommodative.",
        "expected": {"value_sign": "positive", "abs_value_min": 0.10},
    }
    result = run_figure_deviation_case(fixture)
    assert result.passed is False
