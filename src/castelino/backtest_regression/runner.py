"""Per-component runners for the backtest regression suite."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch as _patch

from castelino.backtest_regression.models import CaseResult
from castelino.forecast.risk_off import RiskOffForecast, read_forecast  # patched in tests
from castelino.triggers.risk_gate import evaluate as evaluate_risk_gate


@contextmanager
def with_stubbed_forecast(prob: float):
    """Stub `read_forecast` inside the runner module to return a
    fixture-driven prob. Used by the CLI; tests prefer `unittest.mock.patch`
    directly.

    Patches all three call sites (source module, runner, gate) so any caller —
    including `risk_gate.evaluate()` — sees the fixture's probability.
    """
    fake = RiskOffForecast(
        prob_risk_off=prob,
        as_of=datetime.now(UTC),
        feature_month="",
        target_month="",
    )
    with _patch(
        "castelino.forecast.risk_off.read_forecast",
        return_value=fake,
    ), _patch(
        "castelino.backtest_regression.runner.read_forecast",
        return_value=fake,
    ), _patch(
        "castelino.triggers.risk_gate.read_forecast",
        return_value=fake,
    ):
        yield


def run_risk_off_case(fixture: dict) -> CaseResult:
    """Run one risk-off gate case. Caller must stub `read_forecast` upstream
    (typically via `with_stubbed_forecast`) so the gate sees the fixture's
    `prob_risk_off` instead of whatever is on disk.
    """
    case_id = fixture["case_id"]
    inputs = fixture["inputs"]
    expected = fixture["expected"]

    # Fail fast if caller forgot to stub the forecast.
    forecast = read_forecast()
    if forecast is None or abs(forecast.prob_risk_off - inputs["prob_risk_off"]) > 1e-6:
        return CaseResult(
            case_id=case_id,
            component="risk_off",
            passed=False,
            actual={"error": "forecast not stubbed to fixture prob_risk_off"},
            expected=expected,
            notes="caller must patch read_forecast before invoking",
        )

    # The gate has its own bound import of read_forecast; mirror the
    # stub there so it sees the fixture's prob_risk_off rather than disk.
    with _patch(
        "castelino.triggers.risk_gate.read_forecast",
        return_value=forecast,
    ):
        decision = evaluate_risk_gate(inputs["instrument_id"])
    actual = {
        "action": decision.action,
        "size_multiplier": decision.size_multiplier,
    }
    passed = (
        actual["action"] == expected["action"]
        and abs(actual["size_multiplier"] - expected["size_multiplier"]) < 1e-6
    )
    return CaseResult(
        case_id=case_id,
        component="risk_off",
        passed=passed,
        actual=actual,
        expected=expected,
    )
