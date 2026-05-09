"""Unit tests for the risk-off backtest runner."""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from castelino.backtest_regression.runner import run_risk_off_case


def _stub_forecast(prob: float):
    from castelino.forecast.risk_off import RiskOffForecast
    return RiskOffForecast(
        prob_risk_off=prob,
        as_of=datetime.now(UTC),
        feature_month="2024-08",
        target_month="2024-09",
    )


def test_runner_passes_when_action_matches():
    fixture = {
        "case_id": "calm_spy",
        "inputs": {"prob_risk_off": 0.18, "instrument_id": "SPY"},
        "expected": {"action": "pass", "size_multiplier": 1.0},
    }
    with patch(
        "castelino.backtest_regression.runner.read_forecast",
        return_value=_stub_forecast(0.18),
    ):
        result = run_risk_off_case(fixture)
    assert result.passed is True
    assert result.actual["action"] == "pass"


def test_runner_fails_when_action_diverges():
    fixture = {
        "case_id": "carry_unwind",
        "inputs": {"prob_risk_off": 0.72, "instrument_id": "SPY"},
        "expected": {"action": "pass", "size_multiplier": 1.0},
    }
    with patch(
        "castelino.backtest_regression.runner.read_forecast",
        return_value=_stub_forecast(0.72),
    ):
        result = run_risk_off_case(fixture)
    assert result.passed is False
    assert result.actual["action"] == "veto"


def test_with_stubbed_forecast_context():
    from castelino.backtest_regression.runner import with_stubbed_forecast

    with with_stubbed_forecast(0.55):
        from castelino.forecast.risk_off import read_forecast
        f = read_forecast()
        assert f is not None
        assert abs(f.prob_risk_off - 0.55) < 1e-9


def test_run_all_risk_off_returns_one_result_per_fixture():
    from castelino.backtest_regression.runner import run_all_risk_off
    results = run_all_risk_off()
    assert len(results) == 8
    assert all(r.component == "risk_off" for r in results)
    assert all(r.passed for r in results), [r for r in results if not r.passed]
