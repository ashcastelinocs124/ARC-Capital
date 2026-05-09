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


def test_run_all_figure_deviation_returns_one_per_fixture():
    from castelino.backtest_regression.runner import run_all_figure_deviation
    results = run_all_figure_deviation()
    assert len(results) == 7
    pos = [r for r in results if "value_sign" in r.expected]
    pos_pass_rate = sum(r.passed for r in pos) / max(1, len(pos))
    assert pos_pass_rate >= 0.80, f"positive-case pass rate {pos_pass_rate:.2f} < 0.80"
    neg = [r for r in results if "abs_value_max" in r.expected]
    assert all(r.passed for r in neg), [r for r in neg if not r.passed]


def test_runner_records_lexicon_version_in_actual():
    fixture = {
        "case_id": "synth_v",
        "lexicon": "hawkish_dovish_v1",
        "transcript_excerpt": "Further firming is warranted.",
        "expected": {"value_sign": "positive", "abs_value_min": 0.0},
    }
    result = run_figure_deviation_case(fixture)
    assert "lexicon_version" in result.actual
    assert result.actual["lexicon_version"] == "hawkish_dovish_v1"
