import pytest
from castelino.backtest_regression.models import CaseResult


def test_case_result_minimal():
    r = CaseResult(
        case_id="t1",
        component="risk_off",
        passed=True,
        actual={"action": "pass"},
        expected={"action": "pass"},
    )
    assert r.passed is True
    assert r.notes is None


def test_case_result_rejects_unknown_component():
    with pytest.raises(ValueError):
        CaseResult(
            case_id="t1",
            component="nonsense",
            passed=True,
            actual={},
            expected={},
        )
