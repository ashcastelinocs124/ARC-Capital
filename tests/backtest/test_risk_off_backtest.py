"""Wave 2 Task 2.3 — assert risk-off gate behaviour on hand-curated events."""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from castelino.backtest_regression.runner import run_risk_off_case
from castelino.forecast.risk_off import RiskOffForecast
from tests.backtest.conftest import load_fixtures


def _id(f: dict) -> str:
    return f["case_id"]


def _stub(prob: float) -> RiskOffForecast:
    return RiskOffForecast(
        prob_risk_off=prob,
        as_of=datetime.now(UTC),
        feature_month="",
        target_month="",
    )


@pytest.mark.backtest
@pytest.mark.parametrize("fixture", load_fixtures("risk_off"), ids=_id)
def test_risk_off_event(fixture):
    p = fixture["inputs"]["prob_risk_off"]
    with patch(
        "castelino.backtest_regression.runner.read_forecast",
        return_value=_stub(p),
    ):
        result = run_risk_off_case(fixture)
    assert result.passed, (
        f"{fixture['case_id']}: expected {fixture['expected']}, got {result.actual}"
    )
